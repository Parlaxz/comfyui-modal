// Modal Studio — Backend (Composition/Export Glue)
//
// Public API surface for the Backend page. Imports from focused modules
// and re-exports what consumers need. Keeps renderFeaturesChipGrid as an
// inline helper so tests can find the semantic-button patterns, and
// renderBackend as the main entry point.

import { el, statusBadge } from "./studio-ui.js";
import { createOpsBus } from "./studio-backend-runtime.js";
import { renderWorkspacesSection } from "./studio-backend-workspaces.js";
import { renderDeploymentSection } from "./studio-backend-deployment.js";
import { subscribeStudioSync } from "./studio-sync.js";

// Phase I7: the dead empty-state re-export wrapper was deleted here — zero
// importers since studio-ui.js's renderer became the generic options API
// (I3); page lanes consume that shared primitive directly.

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
    text: "Manage Modal",
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
// ── Main render entry point ──────────────────────────────────────────────

export function renderBackend(state, context) {
  const FOCUS_TABS = ["workspaces", "deployment"];
  // Routing is owned by the shell: read the managed route it hands us rather
  // than parsing the hash here. The shell re-renders this page whenever the
  // route's focus changes, so no page-local hashchange listener is needed.
  function resolveInitialTab() {
    try {
      const route = context && typeof context.getRoute === "function" ? context.getRoute() : null;
      if (route && route.page === "backend" && FOCUS_TABS.indexOf(route.focus) !== -1) {
        return route.focus;
      }
    } catch (_) {}
    return "workspaces";
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

  // Tabs: Workspaces | Deployment. Credentials lives in Settings.
  const tabs = el("div", { class: "comfymodal-studio-backend-tabs" });

  const body = el("div", { class: "comfymodal-studio-backend-body" });

  // Full-width operational section panel
  const opsPanel = el("div", {
    class: "comfymodal-studio-backend-detail",
    "data-testid": "backend-ops-panel",
    style: "flex:1;",
  });

  body.appendChild(opsPanel);

  const OPS_SECTIONS = {
    workspaces: renderWorkspacesSection,
    deployment: renderDeploymentSection,
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

  tabs.appendChild(makeTab("workspaces", "Workspaces"));
  tabs.appendChild(makeTab("deployment", "Deployment"));

  container.appendChild(tabs);
  container.appendChild(body);

  function refreshList() {
    while (opsPanel.firstChild) opsPanel.removeChild(opsPanel.firstChild);
    const section = OPS_SECTIONS[activeTab] || renderWorkspacesSection;
    section(opsPanel, apiBase, _opsBus);
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

  // Deep-link support: Settings' "Open Workspaces" routes through the shell
  // (context.applyRoute({page:"backend", focus:"workspaces"})), which
  // re-renders this page with the new focus. Both the initial mount and
  // in-session navigation therefore arrive via resolveInitialTab().

  refreshList();

  // Store refresh handler so edit wizard can re-render after changes
  container._refreshHandler = () => {
    refreshList();
  };

  return container;
}
