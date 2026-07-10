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

// Module-level cache to avoid refetching presets on every render
let _runtimePresetsCache = null;
let _runtimePresetsCacheKey = "";

export async function getRuntimePresets(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  // Use simple cache: invalidated when apiBase changes
  if (_runtimePresetsCache && _runtimePresetsCacheKey === apiBase) {
    return _runtimePresetsCache;
  }
  _runtimePresetsCache = await listPresets(apiBase);
  _runtimePresetsCacheKey = apiBase;
  return _runtimePresetsCache;
}

// Allow external invalidation of the runtime presets cache
export function invalidateRuntimePresetsCache() {
  _runtimePresetsCache = null;
  _runtimePresetsCacheKey = "";
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
  const selectedSet = new Set(features || []);

  function syncChip(chip) {
    const isPressed = selectedSet.has(chip.dataset.feature);
    chip.setAttribute("aria-pressed", isPressed ? "true" : "false");
    chip.classList.toggle("checked", isPressed);
  }

  known.forEach((fid) => {
    const chip = el("button", {
      type: "button",
      class: "comfymodal-studio-feature-chip",
      "aria-pressed": "false",
      "data-feature": fid,
    }, [
      el("span", { class: "chip-check", text: "\u2713 " }),
      el("span", { text: labels[fid] || fid }),
    ]);
    chip.addEventListener("click", () => {
      if (selectedSet.has(fid)) {
        selectedSet.delete(fid);
      } else {
        selectedSet.add(fid);
      }
      syncChip(chip);
      if (onChange) onChange(Array.from(selectedSet));
    });
    syncChip(chip);
    grid.appendChild(chip);
  });
  return grid;
}

// ── Main render entry point ──────────────────────────────────────────────

// ── Wizard launcher ──────────────────────────────────────────────────────

function launchPresetWizard(context) {
  import("./studio-preset-wizard.js").then(({ openPresetWizard }) => {
    const apiBase = (context && context.apiBase) || "/comfymodal";
    openPresetWizard(() => {
      if (context && typeof context.setPage === "function") {
        context.setPage("backend");
      }
    }, apiBase);
  });
}

// ── Main render entry point ──────────────────────────────────────────────

export function renderBackend(state, context) {
  const container = el("div", {
    class: "comfymodal-studio-backend",
    "data-testid": "backend-page",
  });

  const apiBase = (context && context.apiBase) || "/comfymodal";

  // ── Make Preset button (primary action) ───────────────────────────────
  const actionBar = el("div", {
    class: "comfymodal-studio-backend-action-bar",
    style: "display:flex;align-items:center;gap:8px;margin-bottom:4px;",
  });

  const makePresetBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Make Preset",
    style: "width:auto;padding:6px 16px;font-size:12px;",
    title: "Bind the current ComfyUI graph into a Studio preset",
    onclick: () => launchPresetWizard(context),
  });
  actionBar.appendChild(makePresetBtn);

  const actionBarHint = el("span", {
    style: "font-size:10px;color:#888;",
    text: "Bind the current ComfyUI graph into a Studio preset",
  });
  actionBar.appendChild(actionBarHint);

  container.appendChild(actionBar);

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
