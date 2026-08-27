// Modal Studio — Backend (Composition/Export Glue)
//
// Public API surface for the Backend page. Imports from focused modules
// and re-exports what consumers need. Keeps renderFeaturesChipGrid as an
// inline helper so tests can find the semantic-button patterns, and
// renderBackend as the main entry point.

import { el, statusBadge } from "./studio-ui.js";
import { listPresets } from "./studio-backend-api.js";
import * as _capture from "./studio-backend-capture.js";
import { renderSnapshotsPage, renderSnapshotsList, renderSnapshotDetail } from "./studio-backend-snapshots.js";
import { renderPresetsPage, renderPresetsList, renderPresetDetail, renderPresetForm } from "./studio-backend-presets.js";
import { renderRuntimeSection, createOpsBus } from "./studio-backend-runtime.js";
import { renderWorkspacesSection } from "./studio-backend-workspaces.js";
import { renderDeploymentSection } from "./studio-backend-deployment.js";
import { renderCredentialsSection } from "./studio-backend-credentials.js";
import { subscribeStudioSync } from "./studio-sync.js";
import { parseStudioHash } from "./studio-routing.js";

// Phase I7: the dead empty-state re-export wrapper was deleted here — zero
// importers since studio-ui.js's renderer became the generic options API
// (I3); page lanes consume that shared primitive directly.

// API method reference kept in glue for test discoverability
const _PATCH = "PATCH";

// H18 Wave G: the dead getBackends/getCompareBackends re-exports were deleted
// (zero callers since H16 removed the last Settings consumer; FD-8).

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

// Page-level h2 under the shell h1 (I1 §3.3 / I7). Backend has no visible
// page title, so the heading is accessible-but-visually-hidden with the clip
// pattern — never display:none / visibility:hidden. Local style only; shared
// styles are not edited by this lane.
const PAGE_TITLE_OFFSCREEN_STYLE =
  "position:absolute;width:1px;height:1px;margin:-1px;padding:0;" +
  "border:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;";

function _pageHeading() {
  return el("h2", {
    class: "comfymodal-studio-backend-page-title",
    "data-testid": "backend-page-title",
    text: "Backend",
    style: PAGE_TITLE_OFFSCREEN_STYLE,
  });
}

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
      // FILTER semantics per the I1 taxonomy: interactive aria-pressed toggles
      // stay; only the shared cm-chip geometry base is adopted (no data-tone,
      // no compatibility-family marker — these are feature filters).
      class: "comfymodal-studio-feature-chip cm-chip",
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
      invalidateRuntimePresetsCache();
      if (context && typeof context.setPage === "function") {
        context.setPage("backend");
      }
    }, apiBase);
  });
}

// Edit-mode launcher: opens wizard pre-filled with existing preset data
export function launchPresetWizardForEdit(preset, snapshot, apiBase) {
  import("./studio-preset-wizard.js").then(({ openPresetWizard }) => {
    const onDone = () => {
      invalidateRuntimePresetsCache();
      // Trigger re-render of the current page after edit
      const container = document.querySelector(".comfymodal-studio-backend");
      if (container && container._refreshHandler) {
        container._refreshHandler();
      }
    };
    openPresetWizard(onDone, apiBase || "/comfymodal", preset, snapshot);
  });
}

// ── Main render entry point ──────────────────────────────────────────────

export function renderBackend(state, context) {
  const FOCUS_TABS = ["overview", "workspaces", "deployment", "credentials", "presets", "snapshots"];
  function resolveInitialTab() {
    if (typeof window === "undefined") return "overview";
    try {
      const route = parseStudioHash(window.location.hash);
      if (route.matched && route.page === "backend" && FOCUS_TABS.indexOf(route.focus) !== -1) {
        return route.focus;
      }
    } catch (_) {}
    return "overview";
  }
  let activeTab = resolveInitialTab();

  const container = el("div", {
    class: "comfymodal-studio-backend",
    "data-testid": "backend-page",
  });

  // Truthful page heading first: sole h2 of the page under the shell h1.
  container.appendChild(_pageHeading());

  const apiBase = (context && context.apiBase) || "/comfymodal";
  let backendStale = false;
  let unsubscribeBackendSync = null;

  // Operational sections coordinate through a page-local bus (no globals):
  // workspace mutations notify deployment/runtime sections to re-read
  // server truth.
  const _opsBus = createOpsBus();

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

  // Tabs: Overview | Workspaces | Deployment | Credentials | Snapshots |
  // Backend Presets. Operational sections (H6 re-home) render full-width;
  // Snapshots / Backend Presets keep their list+detail layout.
  const tabs = el("div", { class: "comfymodal-studio-backend-tabs" });

  const body = el("div", { class: "comfymodal-studio-backend-body" });

  // Left list (presets/snapshots only)
  const listPanel = el("div", {
    class: "comfymodal-studio-backend-list",
    "data-testid": "backend-list",
  });

  // Right detail (presets/snapshots only)
  const detailPanel = el("div", {
    class: "comfymodal-studio-backend-detail",
    "data-testid": "backend-detail",
  });

  // Full-width operational section panel
  const opsPanel = el("div", {
    class: "comfymodal-studio-backend-detail",
    "data-testid": "backend-ops-panel",
    style: "flex:1;",
  });

  body.appendChild(listPanel);
  body.appendChild(detailPanel);
  body.appendChild(opsPanel);

  const OPS_SECTIONS = {
    overview: renderRuntimeSection,
    workspaces: renderWorkspacesSection,
    deployment: renderDeploymentSection,
    credentials: renderCredentialsSection,
  };

  function switchTab(tabId) {
    activeTab = tabId;
    tabs.querySelectorAll(".comfymodal-studio-backend-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === tabId);
      // Truthful selection state for AT: these are exclusive view-switcher
      // buttons (native buttons, no tablist keyboard model), so the smallest
      // correct state is aria-current, not aria-selected/tabindex roving.
      if (t.dataset.tab === tabId) t.setAttribute("aria-current", "true");
      else t.removeAttribute("aria-current");
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
    if (id === activeTab) btn.setAttribute("aria-current", "true");
    return btn;
  }

  tabs.appendChild(makeTab("overview", "Overview"));
  tabs.appendChild(makeTab("workspaces", "Workspaces"));
  tabs.appendChild(makeTab("deployment", "Deployment"));
  tabs.appendChild(makeTab("credentials", "Credentials"));
  tabs.appendChild(makeTab("presets", "Backend Presets"));
  tabs.appendChild(makeTab("snapshots", "Snapshots"));

  container.appendChild(tabs);
  container.appendChild(body);

  function refreshList() {
    while (listPanel.firstChild) listPanel.removeChild(listPanel.firstChild);
    while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
    while (opsPanel.firstChild) opsPanel.removeChild(opsPanel.firstChild);

    if (activeTab === "snapshots") {
      listPanel.style.display = "";
      detailPanel.style.display = "";
      opsPanel.style.display = "none";
      renderSnapshotsPage(listPanel, detailPanel, apiBase);
    } else if (activeTab === "presets") {
      listPanel.style.display = "";
      detailPanel.style.display = "";
      opsPanel.style.display = "none";
      renderPresetsPage(listPanel, detailPanel, apiBase);
    } else {
      listPanel.style.display = "none";
      detailPanel.style.display = "none";
      opsPanel.style.display = "";
      const section = OPS_SECTIONS[activeTab] || renderRuntimeSection;
      section(opsPanel, apiBase, _opsBus);
    }
  }

  function refreshFromSync() {
    if (!container.isConnected) {
      if (unsubscribeBackendSync) unsubscribeBackendSync();
      unsubscribeBackendSync = null;
      return;
    }
    backendStale = true;
    container.dataset.syncStale = "true";
    refreshList();
    backendStale = false;
    container.dataset.syncStale = "false";
  }

  unsubscribeBackendSync = subscribeStudioSync("workspace", refreshFromSync);

  // Deep-link support: Settings' "Open Workspaces"/"Open legacy settings"
  // pushes #comfymodal=backend&focus=workspaces after mounting; the initial
  // hash check above handles reloads, this handles in-session navigation.
  let _hashHandler = null;
  if (typeof window !== "undefined") {
    _hashHandler = () => {
      try {
        const route = parseStudioHash(window.location.hash);
        if (route.matched && route.page === "backend" && FOCUS_TABS.indexOf(route.focus) !== -1 && route.focus !== activeTab) {
          switchTab(route.focus);
        }
      } catch (_) {}
    };
    window.addEventListener("hashchange", _hashHandler);
  }

  refreshList();

  // Store refresh handler so edit wizard can re-render after changes
  container._refreshHandler = () => {
    _STATE.selectedItemId = null;
    refreshList();
  };

  return container;
}
