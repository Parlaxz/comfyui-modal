// Modal Studio ΓÇö Settings
//
// Seven-section settings page: General, Generation, Outputs, History,
// Experiments, Interface, Advanced. Preferences-only (H5 ┬º2); the former
// Settings Γû╕ Advanced Γû╕ Legacy group and legacy-tab embedding were retired
// in Phase H14 Wave E.
//
// Contracts:
//  - Exports renderSettings(state, context) (shell PAGES.settings).
//  - state.settings.activeSection behavior is preserved.
//  - Each section keeps a data-section attribute so modal-testing.js can
//    scroll to [data-section=...] via comfymodal.open-section.
//  - Output preferences go through ./studio-output-preferences.js (dynamic
//    import) which dual-writes localStorage + POST /comfymodal/config and
//    keeps its failure-revert behavior.
//  - All new localStorage keys are flat strings.

import { publishStudioSync, subscribeStudioSync } from "./studio-sync.js";
import { renderCredentialsSection } from "./studio-backend-credentials.js";
import {
  loadGoldenProfileSelection,
  saveGoldenProfileSelection,
  clearGoldenProfileSelection,
  loadSkipPlanValidation,
  saveSkipPlanValidation,
  SKIP_PLAN_VALIDATION_KEY,
} from "./studio-playground-state.js";
import {
  getGoldenProfileDeployStatus,
  setGoldenProfileRegion,
  setGoldenProfileGpu,
  setGoldenProfileGpuOrder,
  deployFailureTail,
} from "./studio-backend-api.js";

// ΓöÇΓöÇ Constants ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

const OUTPUT_DEFAULTS = {
  output_format: "original",
  quality: 75,
  webp_lossless_compression: "balanced",
  auto_save_local: false,
  save_folder: "output/modal",
  save_metadata_sidecar: true,
};

const PREVIEW_DEFAULTS = {
  preview_default: "off",
  preview_codec: "webp",
  preview_quality: 70,
};

const REMOTE_INVENTORY_REFRESH_KEY = "comfymodal_remote_inventory_refresh_interval_s";
const REMOTE_INVENTORY_REFRESH_OPTIONS = [
  ["0", "Off"],
  ["60", "1 minute"],
  ["300", "5 minutes"],
  ["900", "15 minutes"],
  ["1800", "30 minutes"],
];
const REMOTE_INVENTORY_REFRESH_DEFAULT = "300";

// Keys managed by the modern Settings page. "Reset all settings" clears
// exactly this set ΓÇö nothing under comfymodal.studio.playground.* or the
// other user-data namespaces is touched.
//
// Guard: every key here must be classified with real reader/writer evidence
// in tests/studio_phase_f4_settings_authority_unit.mjs. Reset-only keys with
// no consumer fail that registry-equality check; removed stale keys must not
// reappear anywhere in this file.
//
// H12: the canvas Cloud/Local run-mode key left this registry ΓÇö it has zero
// modern Studio consumers. The canvas compatibility layer keeps its own
// browser key + window global; modern Settings never writes or resets it.
const MODERN_SETTINGS_KEYS = [
  "comfymodal_gpu",
  "comfymodal_output_format",
  "comfymodal_quality",
  "comfymodal_webp_lossless_compression",
  "comfymodal_auto_save_local",
  "comfymodal_save_folder",
  "comfymodal_save_metadata_sidecar",
  "comfymodal_preview_default",
  "comfymodal_preview_codec",
  "comfymodal_preview_quality",
  "comfymodal_data_saver_default",
  "comfymodal_data_saver_codec",
  "comfymodal_data_saver_quality",
  "comfymodal-studio-history-columns",
  "comfymodal_heavy_tracing",
  "comfymodal.studio.golden.profile.v1",
  "comfymodal-studio-panel-width",
  "comfymodal.studio.playground.carousel-cleared.v1",
  "comfymodal_remote_inventory_refresh_interval_s",
  "comfymodal_skip_plan_validation",
];

const HEAVY_TRACING_LEVELS = ["off", "summary", "detailed", "trace", "trace_verbose"];

// Stable listener handles. The shell re-creates all page DOM on every page
// switch, so element-keyed handlers cannot survive a re-render; tracking
// the last-attached handler at module scope lets us remove it before
// attaching the new one ΓÇö fixing the per-render window listener leak.
let _outputPrefsListener = null;
let _workspaceChangedCleanup = null;
let _goldenDeployPageOwner = 0;

let _outputPrefsModulePromise = null;
function loadOutputPrefsModule() {
  if (!_outputPrefsModulePromise) {
    _outputPrefsModulePromise = import("./studio-output-preferences.js");
  }
  return _outputPrefsModulePromise;
}

// ΓöÇΓöÇ Element helper ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

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
    } else if (k === "dataset") {
      Object.assign(e.dataset, props[k]);
    } else if (k === "checked" || k === "disabled" || k === "hidden" || k === "readonly" || k === "required") {
      // Boolean HTML attributes must use the DOM property, not setAttribute,
      // because setAttribute("checked", false) still marks the element checked.
      if (props[k]) e.setAttribute(k, "");
      else e.removeAttribute(k);
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

// ΓöÇΓöÇ Preview preference helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function getPreviewPrefs() {
  const saverDefault = localStorage.getItem("comfymodal_data_saver_default") ?? localStorage.getItem("comfymodal_preview_default");
  const saverCodec = localStorage.getItem("comfymodal_data_saver_codec") ?? localStorage.getItem("comfymodal_preview_codec");
  const saverQualityRaw = localStorage.getItem("comfymodal_data_saver_quality") ?? localStorage.getItem("comfymodal_preview_quality");
  return {
    preview_default: saverDefault === "on"
      ? "on" : PREVIEW_DEFAULTS.preview_default,
    preview_codec: saverCodec === "webp"
      ? "webp" : PREVIEW_DEFAULTS.preview_codec,
    preview_quality: parseInt(saverQualityRaw, 10) || PREVIEW_DEFAULTS.preview_quality,
  };
}

function setPreviewPrefs(p) {
  return loadOutputPrefsModule().then(function (m) {
    return m.setOutputPreferences(p);
  });
}

// Merge current preview prefs into the shared window object without writing
// localStorage (used after resets that remove the keys).
function syncWindowOutputOptions() {
  try {
    const base = (window._comfyModalOutputOptions && typeof window._comfyModalOutputOptions === "object")
      ? window._comfyModalOutputOptions
      : {};
    window._comfyModalOutputOptions = Object.assign({}, base, getPreviewPrefs());
  } catch (_) {}
}

// ΓöÇΓöÇ Shared row builders ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function settingsRow(label, valueEl) {
  return el("div", { class: "comfymodal-studio-settings-row" }, [
    el("span", { class: "comfymodal-studio-settings-row-label", text: label }),
    valueEl || el("span", { class: "comfymodal-studio-settings-row-value", text: "\u2014" }),
  ]);
}

function settingsValue(value) {
  return el("span", { class: "comfymodal-studio-settings-row-value", text: String(value) });
}

function selectWithOptions(options, testid) {
  const sel = el("select", { class: "comfymodal-input", "data-testid": testid });
  for (const [value, label] of options) {
    sel.appendChild(el("option", { value: value, text: label }));
  }
  return sel;
}

// ΓöÇΓöÇ renderSettings (public) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

export function renderSettings(state, context) {
  if (_workspaceChangedCleanup) _workspaceChangedCleanup();
  const goldenDeployPageOwner = ++_goldenDeployPageOwner;
  const container = el("div", { class: "comfymodal-studio-settings" });
  let settingsStale = false;
  let unsubscribeSettingsSync = null;

  function refreshFromSync() {
    if (!container.isConnected) {
      if (unsubscribeSettingsSync) unsubscribeSettingsSync();
      unsubscribeSettingsSync = null;
      return;
    }
    settingsStale = true;
    container.dataset.syncStale = "true";
    rebuildPage();
    settingsStale = false;
    container.dataset.syncStale = "false";
  }

  unsubscribeSettingsSync = subscribeStudioSync("settings", refreshFromSync);

  // Truthful page h2 under the shell h1 (I1 ┬º3.3 / I7). Settings has no
  // visible page title, so the heading is accessible-but-visually-hidden
  // with the clip pattern ΓÇö never display:none / visibility:hidden.
  // Section headings stay h3 and the Runtime & Backend group stays h4,
  // exactly as frozen.
  container.appendChild(el("h2", {
    class: "comfymodal-studio-settings-page-title",
    "data-testid": "settings-page-title",
    text: "Settings",
    style: "position:absolute;width:1px;height:1px;margin:-1px;padding:0;" +
      "border:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;",
  }));

  const apiBase = (context && context.apiBase) || "/comfymodal";
  // Heavy-tracing server truth: persisted (.profile_config.json) vs what the
  // current process is executing. Both come from GET /profile/level; the
  // restart banner compares these, never the browser-stored selection.
  let persistedTracingLevel = null;
  let effectiveTracingLevel = null;
  let goldenProfiles = [];
  let goldenProfilesError = null;
  let activeGoldenDeployPoll = null;
  let goldenDeployGeneration = 0;
  // Favorites are a personal, per-browser preference: they mark which profiles a
  // user cares about without changing what is selected or deployed.
  const FAVORITE_PROFILES_KEY = "comfymodal.studio.golden.favorites.v1";
  function favoriteProfileNames() {
    try {
      const raw = localStorage.getItem(FAVORITE_PROFILES_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return new Set(Array.isArray(parsed) ? parsed.filter((n) => typeof n === "string") : []);
    } catch (e) {
      return new Set();
    }
  }
  function toggleFavoriteProfile(name) {
    const names = favoriteProfileNames();
    if (names.has(name)) names.delete(name);
    else names.add(name);
    try {
      localStorage.setItem(FAVORITE_PROFILES_KEY, JSON.stringify(Array.from(names)));
    } catch (e) {
      // A full or unavailable localStorage must not break the settings panel.
    }
  }

  // ΓöÇΓöÇ Pending-restart banner (persistent across rebuilds) ΓöÇΓöÇ
  const bannerEl = el("div", {
    class: "comfymodal-settings-restart-banner",
    "data-testid": "settings-restart-banner",
    style: "display:none;",
  });
  bannerEl.textContent = "Heavy tracing change requires a ComfyUI restart to take effect.";
  container.appendChild(bannerEl);

  // ΓöÇΓöÇ Search ΓöÇΓöÇ
  const searchResultEl = el("div", {
    class: "comfymodal-settings-search-results",
    "data-testid": "settings-search-results",
    style: "display:none;",
  });
  const searchInput = el("input", {
    type: "search",
    class: "comfymodal-input comfymodal-settings-search",
    placeholder: "Search settings...",
    "data-testid": "settings-search",
    "aria-label": "Search settings",
  });
  const clearSearch = el("button", {
    type: "button", class: "comfymodal-settings-search-clear", text: "Clear",
    "aria-label": "Clear settings search",
    onclick: () => { searchInput.value = ""; searchInput.focus(); applyFilter(); },
  });
  const searchWrap = el("div", { class: "comfymodal-settings-search-wrap" }, [searchInput, clearSearch, searchResultEl]);
  container.appendChild(searchWrap);

  const sectionsHost = el("div", { class: "comfymodal-settings-sections" });
  container.appendChild(sectionsHost);

  const tabOrder = ["generation", "outputs", "accounts", "interface", "advanced"];
  const tabLabels = { generation: "Generation", outputs: "Outputs", accounts: "Accounts & Tokens", interface: "Interface", advanced: "Advanced" };
  let selectedTab = ["generation", "outputs", "accounts", "interface", "advanced"].includes(state?.settings?.activeSection)
    ? state.settings.activeSection : "generation";
  const tabsHost = el("div", { class: "comfymodal-studio-settings-tabs", role: "tablist", "aria-label": "Settings categories" });
  container.insertBefore(tabsHost, sectionsHost);
  const tabButtons = new Map();

  function selectTab(tabId, focus) {
    if (!tabOrder.includes(tabId)) tabId = "generation";
    selectedTab = tabId;
    if (state && state.settings) state.settings.activeSection = tabId;
    tabButtons.forEach((button, id) => {
      const active = id === selectedTab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.setAttribute("tabindex", active ? "0" : "-1");
    });
    sectionsHost.querySelectorAll("[data-settings-tab]").forEach((panel) => {
      const active = panel.dataset.settingsTab === selectedTab;
      panel.hidden = !active;
      panel.setAttribute("aria-hidden", active ? "false" : "true");
    });
    if (focus) tabButtons.get(selectedTab).focus();
    // A category choice is an explicit request to leave search mode. Re-run
    // the normal filter path so hidden rows and the result summary cannot
    // outlive the newly selected panel.
    if ((searchInput.value || "").trim()) {
      searchInput.value = "";
      applyFilter();
    }
  }

  tabOrder.forEach((tabId, index) => {
    const button = el("button", {
      type: "button", class: "comfymodal-studio-settings-tab", role: "tab",
      id: "settings-tab-" + tabId, "aria-controls": "settings-panel-" + tabId,
      text: tabLabels[tabId],
    });
    button.addEventListener("click", () => selectTab(tabId, true));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const current = tabOrder.indexOf(tabId);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabOrder.length - 1
        : (current + (event.key === "ArrowRight" ? 1 : -1) + tabOrder.length) % tabOrder.length;
      selectTab(tabOrder[next], true);
    });
    tabsHost.appendChild(button);
    tabButtons.set(tabId, button);
  });

  const footerEl = el("div", { class: "comfymodal-settings-footer" });
  container.appendChild(footerEl);

  // ΓöÇΓöÇ Search filter (state is local to this render) ΓöÇΓöÇ
  function applyFilter() {
    const q = (searchInput.value || "").trim().toLowerCase();
    let matched = 0;
    const groups = new Map();
    sectionsHost.querySelectorAll("[data-search]").forEach((unit) => {
      const hit = !q || (unit.dataset.search || "").indexOf(q) !== -1;
      unit.classList.toggle("comfymodal-settings-row-hidden", !hit);
      if (hit) {
        matched++;
        const panel = unit.closest("[data-settings-tab]");
        if (panel) groups.set(panel.dataset.settingsTab, (groups.get(panel.dataset.settingsTab) || 0) + 1);
      }
    });
    sectionsHost.querySelectorAll("[data-settings-tab]").forEach((section) => {
      const anyVisible = section.querySelectorAll(
        "[data-search]:not(.comfymodal-settings-row-hidden)"
      ).length > 0;
      section.hidden = q ? !anyVisible : section.dataset.settingsTab !== selectedTab;
      section.setAttribute("aria-hidden", section.hidden ? "true" : "false");
    });
    if (q) {
      while (searchResultEl.firstChild) searchResultEl.removeChild(searchResultEl.firstChild);
      if (matched === 0) {
        searchResultEl.appendChild(el("span", { class: "comfymodal-settings-search-empty", text: "No settings match your search" }));
      } else {
        searchResultEl.appendChild(el("span", {
          class: "comfymodal-settings-search-summary",
          text: matched + " matching setting" + (matched === 1 ? "" : "s") + " across " + groups.size + " tabs",
        }));
        groups.forEach((count, id) => searchResultEl.appendChild(el("button", {
          type: "button", class: "comfymodal-settings-search-group", text: tabLabels[id] + " · " + count,
           onclick: () => selectTab(id, true),
        })));
      }
      searchResultEl.style.display = "block";
    } else {
      searchResultEl.textContent = "";
      searchResultEl.style.display = "none";
    }
    if (!q) selectTab(selectedTab, false);
  }

  searchInput.addEventListener("input", applyFilter);

  // ΓöÇΓöÇ Helpers used by resets ΓöÇΓöÇ
  function removeKeys(keys) {
    for (const key of keys) {
      try { localStorage.removeItem(key); } catch (_) {}
    }
  }

  function showTransient(testid, text) {
    const btn = sectionsHost.querySelector('[data-testid="' + testid + '"]');
    const target = btn
      ? btn.closest(".comfymodal-settings-section-actions")
        || btn.closest(".comfymodal-settings-control")
        || btn.parentNode
      : null;
    if (!target) return;
    const span = el("span", { class: "comfymodal-settings-reset-confirm", text: text });
    target.appendChild(span);
    setTimeout(() => { if (span.parentNode) span.parentNode.removeChild(span); }, 2600);
  }

  // ΓöÇΓöÇ Per-section reset implementations ΓöÇΓöÇ
  // F8: the server owns the persisted GPU, so resets POST the canonical
  // default back to /config (server + persistence) instead of only
  // clearing the browser display cache.
  async function fetchDefaultGpu() {
    try {
      const resp = await fetch(apiBase + "/config");
      if (resp.ok) {
        const cfg = await resp.json();
        if (cfg && cfg.default_gpu) return cfg.default_gpu;
      }
    } catch (_) {}
    return "rtx-pro-6000";
  }

  const resets = {
    generation: async () => {
      removeKeys(["comfymodal_gpu", "comfymodal_preview_default", "comfymodal_preview_codec", "comfymodal_preview_quality", "comfymodal_data_saver_default", "comfymodal_data_saver_codec", "comfymodal_data_saver_quality"]);
      try {
        const m = await loadOutputPrefsModule();
        await m.setOutputPreferences({
          preview_default: PREVIEW_DEFAULTS.preview_default,
          preview_codec: PREVIEW_DEFAULTS.preview_codec,
          preview_quality: PREVIEW_DEFAULTS.preview_quality,
          data_saver_default: PREVIEW_DEFAULTS.preview_default,
          data_saver_codec: PREVIEW_DEFAULTS.preview_codec,
          data_saver_quality: PREVIEW_DEFAULTS.preview_quality,
        });
      } catch (_) {}
      try {
        const defaultGpu = await fetchDefaultGpu();
        const resp = await fetch(apiBase + "/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gpu: defaultGpu }),
        });
        if (resp.ok) publishStudioSync("settings");
      } catch (_) {}
      clearGoldenProfileSelection();
      try {
        await fetch(apiBase + "/config", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ golden_profile: null }),
        });
      } catch (_) {}
    },
    outputs: async () => {
      removeKeys([
        "comfymodal_output_format",
        "comfymodal_quality",
        "comfymodal_webp_lossless_compression",
        "comfymodal_auto_save_local",
        "comfymodal_save_folder",
        "comfymodal_save_metadata_sidecar",
      ]);
      try {
        const m = await loadOutputPrefsModule();
        await m.setOutputPreferences(Object.assign({}, OUTPUT_DEFAULTS));
      } catch (_) {}
      syncWindowOutputOptions();
    },
    interface: async () => {
      removeKeys(["comfymodal-studio-panel-width", "comfymodal.studio.playground.carousel-cleared.v1", REMOTE_INVENTORY_REFRESH_KEY, "comfymodal-studio-history-columns"]);
    },
    advanced: async () => {
      removeKeys(["comfymodal_heavy_tracing", SKIP_PLAN_VALIDATION_KEY]);
      try {
        await fetch(apiBase + "/profile/level", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ level: "off" }),
        });
      } catch (_) {}
      // Re-enable the safety gates server-side too (reset = fail-closed).
      try {
        await fetch(apiBase + "/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ skip_plan_validation: false }),
        });
      } catch (_) {}
    },
  };

  async function runSectionReset(key) {
    await resets[key]();
    publishStudioSync("settings");
    rebuildPage();
    showTransient("settings-reset-" + key, "Section reset to defaults");
  }

  async function runResetAll() {
    const ok = confirm(
      "Reset all Studio preferences to defaults. " +
      "The GPU selection is reset to the default. " +
      "Your Workflows, run History, drafts, and assets are NOT affected."
    );
    if (!ok) return;
    removeKeys(MODERN_SETTINGS_KEYS);
    clearGoldenProfileSelection();
    try {
      const defaultGpu = await fetchDefaultGpu();
      const resp = await fetch(apiBase + "/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gpu: defaultGpu }),
      });
      if (resp.ok) publishStudioSync("settings");
    } catch (_) {}
    try {
      const m = await loadOutputPrefsModule();
      await m.setOutputPreferences(Object.assign({}, OUTPUT_DEFAULTS));
    } catch (_) {}
    syncWindowOutputOptions();
    try {
      await fetch(apiBase + "/config", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ golden_profile: null }),
      });
    } catch (_) {}
    try {
      await fetch(apiBase + "/profile/level", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: "off" }),
      });
    } catch (_) {}
    publishStudioSync("settings");
    rebuildPage();
    const confirmEl = el("span", { class: "comfymodal-settings-reset-confirm", text: "All settings reset to defaults" });
    const resetButton = sectionsHost.querySelector('[data-testid="settings-reset-all"]');
    (resetButton && resetButton.parentNode ? resetButton.parentNode : sectionsHost).appendChild(confirmEl);
    setTimeout(() => { if (confirmEl.parentNode) confirmEl.parentNode.removeChild(confirmEl); }, 2600);
  }

  // ΓöÇΓöÇ Section builders ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

  function buildSectionHeader(title, resetTestid) {
    const head = el("div", { class: "comfymodal-studio-settings-section-head" });
    head.appendChild(el("h3", { text: title }));
    // Sections with nothing to reset (informational-only, e.g. Experiments)
    // pass no resetTestid and render no reset button.
    if (resetTestid) {
      const actions = el("div", { class: "comfymodal-settings-section-actions" });
      actions.appendChild(el("button", {
        type: "button",
        class: "comfymodal-settings-reset-section-btn",
        "data-testid": resetTestid,
        text: "Reset section",
        // Every reset control names its section: the five section resets
        // previously shared the identical accessible name "Reset section".
        "aria-label": "Reset " + title + " section",
        onclick: () => runSectionReset(resetTestid.replace("settings-reset-", "")),
      }));
      head.appendChild(actions);
    }
    return head;
  }

  // A searchable unit: settings row + optional hint line.
  function controlRow(label, controlEl, hint, searchExtra) {
    const wrap = el("div", {
      class: "comfymodal-settings-control",
      "data-search": (label + " " + (hint || "") + " " + (searchExtra || "")).toLowerCase(),
    });
    wrap.appendChild(settingsRow(label, controlEl));
    if (hint) wrap.appendChild(el("div", { class: "comfymodal-studio-settings-hint", text: hint }));
    return wrap;
  }

  function infoRow(text) {
    return el("div", { class: "comfymodal-settings-control", "data-search": text.toLowerCase() }, [
      el("p", { class: "comfymodal-studio-settings-info", text: text }),
    ]);
  }

  // ΓöÇΓöÇ 2. Generation ΓöÇΓöÇ
  function buildGenerationSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "generation", "data-settings-tab": "generation", id: "settings-panel-generation", role: "tabpanel", "aria-labelledby": "settings-tab-generation" });
    section.appendChild(buildSectionHeader("Generation", "settings-reset-generation"));

    // H12: the V1/V2 Execution Engine selector is retired ΓÇö Modal V2 is the
    // only public Studio engine, so there is no engine choice to expose.
    // GPU remains the sole execution-affecting preference in Settings.

    // GPU (server-backed; localStorage comfymodal_gpu is a display cache only)
    const gpuSelect = el("select", { class: "comfymodal-input", "data-testid": "settings-gpu" });
    // Placeholder until refreshGpuConfig replaces the options: an empty
    // select renders as a blank dropdown and reads as missing state.
    gpuSelect.appendChild(el("option", { value: "", text: "Loading GPUs…", disabled: true, selected: true }));
    gpuSelect.style.cssText = "width:100%;font-size:11px;padding:3px 6px;";
    section.appendChild(controlRow("GPU", gpuSelect, "You only pay while generating.", "gpu graphics card"));
    section.appendChild(el("div", {
      class: "comfymodal-studio-settings-hint",
      "data-testid": "settings-gpu-status",
      style: "display:none;",
    }));

    // Data Saver default (global, server-backed; testids keep legacy preview names)
    const previewDefault = selectWithOptions([["off", "Off"], ["on", "On"]], "settings-preview-default");
    previewDefault.value = getPreviewPrefs().preview_default;
    previewDefault.addEventListener("change", () => {
      const previous = previewDefault.value === "on" ? "off" : "on";
      setPreviewPrefs({ preview_default: previewDefault.value }).catch(() => {
        previewDefault.value = previous;
      });
    });
    section.appendChild(controlRow("Data Saver default", previewDefault, "Global default for Data Saver results. Original is always stored; Data Saver serves the small file. Applies to new submissions only.", "data saver default preview default"));

    const previewCodec = selectWithOptions([["webp", "WebP"]], "settings-preview-codec");
    previewCodec.value = getPreviewPrefs().preview_codec;
    previewCodec.addEventListener("change", () => {
      const previous = previewCodec.value === "webp" ? "webp" : PREVIEW_DEFAULTS.preview_codec;
      setPreviewPrefs({ preview_codec: previewCodec.value }).catch(() => { previewCodec.value = previous; });
    });
    section.appendChild(controlRow("Data Saver codec", previewCodec, "Codec used for Data Saver files.", "data saver codec preview codec"));

    const previewQuality = el("input", { type: "range", min: "1", max: "100", step: "1", value: String(getPreviewPrefs().preview_quality), class: "comfymodal-settings-range", "data-testid": "settings-preview-quality", "aria-label": "Data Saver quality" });
    const previewQualityVal = el("span", { class: "comfymodal-settings-range-value", "data-testid": "settings-preview-quality-value", text: previewQuality.value });
    previewQuality.addEventListener("input", () => { previewQualityVal.textContent = previewQuality.value; });
    previewQuality.addEventListener("change", () => {
      const previous = previewQuality.value;
      setPreviewPrefs({ preview_quality: parseInt(previewQuality.value, 10) || PREVIEW_DEFAULTS.preview_quality }).catch(() => { previewQuality.value = previous; previewQualityVal.textContent = previous; });
    });
    section.appendChild(controlRow("Data Saver quality", el("div", { class: "comfymodal-settings-range-wrap" }, [previewQuality, previewQualityVal]), "Compression quality for Data Saver files (1-100).", "data saver quality preview quality"));

    const goldenProfileWrap = el("div", { class: "comfymodal-settings-control", "data-search": "golden profile owner method deployed undeployed runtime" });
    goldenProfileWrap.appendChild(settingsRow("Golden profile", el("div", { "data-testid": "settings-golden-profile-host", style: "width:100%;" })));
    goldenProfileWrap.appendChild(el("div", { class: "comfymodal-studio-settings-hint", text: "Select the server-catalogued execution profile used for generation." }));
    section.appendChild(goldenProfileWrap);

    // One-time H12 migration notice (surfaced only when this server process
    // migrated a persisted retired engine value at startup).
    section.appendChild(el("div", { "data-testid": "settings-migration-notice-host" }));
    return section;
  }

  // ΓöÇΓöÇ 3. Outputs ΓöÇΓöÇ
  function buildOutputsSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "outputs", "data-settings-tab": "outputs", id: "settings-panel-outputs", role: "tabpanel", "aria-labelledby": "settings-tab-outputs" });
    section.appendChild(buildSectionHeader("Outputs", "settings-reset-outputs"));
    section.appendChild(el("div", { "data-testid": "settings-outputs-host" }));
    return section;
  }

  // ΓöÇΓöÇ 6. Interface ΓöÇΓöÇ
  function buildInterfaceSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "interface", "data-settings-tab": "interface", id: "settings-panel-interface", role: "tabpanel", "aria-labelledby": "settings-tab-interface" });
    section.appendChild(buildSectionHeader("Interface", "settings-reset-interface"));

    const columnsSelect = el("select", { class: "comfymodal-input", "data-testid": "settings-history-columns" });
    for (let n = 2; n <= 8; n++) columnsSelect.appendChild(el("option", { value: String(n), text: String(n) }));
    let savedColumns = 6;
    try { savedColumns = parseInt(localStorage.getItem("comfymodal-studio-history-columns"), 10) || 6; } catch (_) {}
    columnsSelect.value = String(savedColumns >= 2 && savedColumns <= 8 ? savedColumns : 6);
    columnsSelect.addEventListener("change", () => { try { localStorage.setItem("comfymodal-studio-history-columns", columnsSelect.value); } catch (_) {} });
    section.appendChild(controlRow("History grid columns", columnsSelect, "Number of columns in the run history grid.", "history history grid columns"));

    const inventoryRefresh = selectWithOptions(REMOTE_INVENTORY_REFRESH_OPTIONS, "settings-remote-inventory-refresh");
    let savedInventoryRefresh = REMOTE_INVENTORY_REFRESH_DEFAULT;
    try {
      const stored = localStorage.getItem("comfymodal_remote_inventory_refresh_interval_s");
      if (REMOTE_INVENTORY_REFRESH_OPTIONS.some(([value]) => value === stored)) savedInventoryRefresh = stored;
    } catch (_) {}
    inventoryRefresh.value = savedInventoryRefresh;
    inventoryRefresh.addEventListener("change", () => {
      try { localStorage.setItem("comfymodal_remote_inventory_refresh_interval_s", inventoryRefresh.value); } catch (_) {}
    });
    section.appendChild(controlRow(
      "Remote inventory refresh",
      inventoryRefresh,
      "Refreshes lightweight remote inventory only while Studio is open and this browser page is visible and focused.",
      "remote inventory refresh visible focused polling",
    ));

    const resetLayoutBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-settings-panel-reset",
      "data-testid": "settings-reset-panel-layout",
      text: "Reset panel layout",
    });
    resetLayoutBtn.addEventListener("click", () => {
      if (!confirm("Reset the Studio panel layout (panel width and carousel dismissal state)? This does not affect your data.")) return;
      removeKeys(["comfymodal-studio-panel-width", "comfymodal.studio.playground.carousel-cleared.v1"]);
      showTransient("settings-reset-panel-layout", "Layout preferences cleared");
    });

    const wrap = el("div", { class: "comfymodal-settings-control", "data-search": "reset panel layout" });
    wrap.appendChild(settingsRow("Panel layout", resetLayoutBtn));
    section.appendChild(wrap);
    section.appendChild(infoRow("Keyboard shortcuts follow ComfyUI defaults."));
    return section;
  }

  // ΓöÇΓöÇ 7. Advanced ΓöÇΓöÇ
  function buildAdvancedSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "advanced", "data-settings-tab": "advanced", id: "settings-panel-advanced", role: "tabpanel", "aria-labelledby": "settings-tab-advanced" });
    section.appendChild(buildSectionHeader("Advanced", "settings-reset-advanced"));

    // Heavy tracing (server-backed via /profile/level, local key for the selection)
    const tracingSelect = selectWithOptions([
      ["off", "Off"],
      ["summary", "Summary"],
      ["detailed", "Detailed"],
      ["trace", "Trace"],
       ["trace_verbose", "Verbose trace"],
    ], "settings-heavy-tracing");
    const storedTracing = localStorage.getItem("comfymodal_heavy_tracing") || "off";
    tracingSelect.value = HEAVY_TRACING_LEVELS.indexOf(storedTracing) !== -1 ? storedTracing : "off";

    const restartBadge = el("span", { class: "comfymodal-settings-restart-badge", text: "Requires ComfyUI restart" });
    const tracingRow = el("div", { class: "comfymodal-studio-settings-row" }, [
      el("span", { class: "comfymodal-studio-settings-row-label", text: "Heavy tracing" }),
      el("div", { class: "comfymodal-settings-row-value-inline" }, [tracingSelect, restartBadge]),
    ]);
    const tracingWrap = el("div", {
      class: "comfymodal-settings-control",
      "data-search": "heavy tracing profile level requires comfyui restart",
    });
    tracingWrap.appendChild(tracingRow);
    tracingWrap.appendChild(el("div", { class: "comfymodal-studio-settings-hint", text: "Capture execution trace data. Applies after a ComfyUI restart." }));
    section.appendChild(tracingWrap);

    // Plan validation escape hatch: local key drives execution gating
    // synchronously (no run-context reload needed); the server persists its
    // own mirror via POST /comfymodal/config for headless/API callers.
    // Temporary triage for validation false negatives (e.g. frontend-only
    // Set/Get nodes). Off by default; skipping can push bad graphs to Modal.
    const skipValidation = el("input", {
      type: "checkbox",
      checked: loadSkipPlanValidation(),
      class: "comfymodal-settings-checkbox",
      "data-testid": "settings-skip-plan-validation",
      "aria-label": "Skip plan validation",
    });
    skipValidation.addEventListener("change", () => {
      const next = skipValidation.checked;
      const prev = !next;
      saveSkipPlanValidation(next);
      const base = (context && context.apiBase) || "/comfymodal";
      fetch(base + "/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skip_plan_validation: next }),
      }).then((resp) => {
        if (!resp.ok) throw new Error("skip_plan_validation rejected");
        // Merge into the warm run-options cache so the next Run honors the
        // toggle without waiting for a fresh GET /config.
        try {
          window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", {
            detail: { skip_plan_validation: next },
          }));
        } catch (_) {}
        publishStudioSync("settings");
      }).catch(() => {
        saveSkipPlanValidation(prev);
        skipValidation.checked = prev;
      });
    });
    const skipWrap = el("div", {
      class: "comfymodal-settings-control",
      "data-search": "skip plan validation safety gate escape hatch",
    });
    skipWrap.appendChild(settingsRow("Skip plan validation", skipValidation));
    skipWrap.appendChild(el("div", { class: "comfymodal-studio-settings-hint", text: "Temporary only: bypass the host plan-validation gate that blocks runs on unknown node types. Invalid graphs fail remotely instead." }));
    section.appendChild(skipWrap);

    // Runtime & Backend group
    const runtimeGroup = el("div", {
      class: "comfymodal-settings-group",
      "data-search": "runtime manage modal deploy state credentials token workspace workspaces edit",
    });
    runtimeGroup.appendChild(el("h4", { class: "comfymodal-settings-group-title", text: "Runtime & Manage Modal" }));

    const deployWrap = el("div", { class: "comfymodal-settings-control", "data-search": "deploy state" });
    deployWrap.appendChild(settingsRow("Deploy state", el("span", {
      class: "comfymodal-studio-settings-row-value",
      "data-testid": "settings-deploy-state",
      text: "\u2014",
    })));
    runtimeGroup.appendChild(deployWrap);


    const backendLinkWrap = el("div", { class: "comfymodal-settings-control", "data-search": "open manage modal" });
    const backendLink = el("a", {
      class: "comfymodal-settings-link",
      "data-testid": "settings-open-backend",
      text: "Open Manage Modal",
      href: "#",
    });
    backendLink.addEventListener("click", (e) => {
      e.preventDefault();
      if (context && context.setPage) context.setPage("backend");
    });
    backendLinkWrap.appendChild(settingsRow("Manage Modal", backendLink));
    runtimeGroup.appendChild(backendLinkWrap);

    // Workspace editing lives in the Manage Modal tab. Navigation goes
    // through the shell's routing authority (context.applyRoute) rather than
    // writing history here; the Backend page consumes the focus identity and
    // switches its own tab, so no click-after-timeout hack is needed.
    function openWorkspaces(e) {
      e.preventDefault();
      if (context && typeof context.applyRoute === "function") {
        context.applyRoute({ page: "backend", focus: "workspaces" });
        return;
      }
      if (context && typeof context.setPage === "function") {
        context.setPage("backend");
      }
    }

    const workspacesLinkWrap = el("div", {
      class: "comfymodal-settings-control",
      "data-search": "workspace workspaces legacy edit",
    });
    const workspacesLink = el("a", {
      class: "comfymodal-settings-link",
      "data-testid": "settings-open-workspaces",
      text: "Open Workspaces",
      href: "#",
      "aria-label": "Open workspace editor",
    });
    workspacesLink.addEventListener("click", openWorkspaces);
    workspacesLinkWrap.appendChild(settingsRow("Workspaces", workspacesLink));
    runtimeGroup.appendChild(workspacesLinkWrap);

    section.appendChild(runtimeGroup);

    const resetAllWrap = el("div", { class: "comfymodal-settings-control", "data-search": "reset all settings preferences defaults" });
    resetAllWrap.appendChild(el("p", { class: "comfymodal-studio-settings-hint", text: "Reset every preference managed by this page. Credentials and user data are not affected." }));
    resetAllWrap.appendChild(el("button", { type: "button", class: "comfymodal-destructive-btn comfymodal-settings-reset-all-btn", "data-testid": "settings-reset-all", text: "Reset all settings", onclick: runResetAll }));
    section.appendChild(resetAllWrap);

    return section;
  }

  function buildAccountsSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "accounts", "data-settings-tab": "accounts", id: "settings-panel-accounts", role: "tabpanel", "aria-labelledby": "settings-tab-accounts" });
    section.appendChild(buildSectionHeader("Accounts & Tokens", ""));
    const credentialsWrap = el("div", { class: "comfymodal-settings-control", "data-search": "credentials token huggingface civitai modal account workspace" });
    credentialsWrap.appendChild(el("p", { class: "comfymodal-studio-settings-hint", text: "Connection status and model-provider tokens. Credentials are never included in reset actions." }));
    renderCredentialsSection(credentialsWrap, (context && context.apiBase) || "/comfymodal");
    section.appendChild(credentialsWrap);
    return section;
  }

  // ΓöÇΓöÇ Assembly + async refreshes ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

  function buildSections() {
    const sections = [
      buildGenerationSection(),
      buildOutputsSection(),
      buildAccountsSection(),
      buildInterfaceSection(),
      buildAdvancedSection(),
    ];
    return { sections: sections, footer: null };
  }

  function rebuildPage() {
    while (sectionsHost.firstChild) sectionsHost.removeChild(sectionsHost.firstChild);
    while (footerEl.firstChild) footerEl.removeChild(footerEl.firstChild);
    const { sections, footer } = buildSections();
    for (const s of sections) sectionsHost.appendChild(s);
    if (footer) footerEl.appendChild(footer);
    applyFilter();
    refreshEngineMigrationNotice(apiBase);
    refreshGpuConfig(apiBase);
    refreshDeployStatus(apiBase);
    refreshOutputsPrefs(apiBase);
    refreshProfileLevel(apiBase);
    refreshGoldenProfiles(apiBase);
    refreshSkipPlanValidation(apiBase);
  }

  // ── Plan-validation escape hatch refresh ──
  // Local key is the execution-gating authority, so it wins when present;
  // the server value backfills an unset local key (fresh browser/profile).
  function refreshSkipPlanValidation(base) {
    const box = sectionsHost.querySelector('[data-testid="settings-skip-plan-validation"]');
    if (!box) return;
    if (loadSkipPlanValidation()) {
      box.checked = true;
      return;
    }
    fetch(base + "/config")
      .then((r) => r.json())
      .then((cfg) => {
        if (cfg && cfg.skip_plan_validation === true) {
          saveSkipPlanValidation(true);
          box.checked = true;
        } else {
          box.checked = false;
        }
      })
      .catch(() => {});
  }

  // ΓöÇΓöÇ H12 engine migration notice (server-backed, one-time) ΓöÇΓöÇ
  // Surfaced only when this server process migrated a persisted retired
  // execution_mode (v1/legacy/shadow/garbage) to V2 at startup.
  function refreshEngineMigrationNotice(base) {
    const host = sectionsHost.querySelector('[data-testid="settings-migration-notice-host"]');
    if (!host) return;
    fetch(base + "/config")
      .then((r) => r.json())
      .then((cfg) => {
        const notice = cfg && cfg.engine_migration_notice;
        if (!notice) return;
        while (host.firstChild) host.removeChild(host.firstChild);
        const wrap = el("div", {
          class: "comfymodal-settings-control",
          "data-testid": "settings-engine-migration-notice",
          "data-search": "engine v1 retired migrated v2 notice",
        });
        wrap.appendChild(el("p", { class: "comfymodal-studio-settings-info", text: String(notice) }));
        host.appendChild(wrap);
      })
      .catch(() => {});
  }

  // ΓöÇΓöÇ GPU refresh (server truth first; localStorage as cache only) ΓöÇΓöÇ
  function refreshGpuConfig(base) {
    const gpuSelect = sectionsHost.querySelector('[data-testid="settings-gpu"]');
    const gpuStatus = sectionsHost.querySelector('[data-testid="settings-gpu-status"]');
    if (!gpuSelect) return;

    fetch(base + "/config")
      .then((r) => r.json())
      .then((cfg) => {
        const options = Array.isArray(cfg && cfg.available_gpus)
          ? cfg.available_gpus.filter((o) => o && typeof o.value === "string" && o.value)
          : [];
        const values = new Set(options.map((o) => o.value));
        const serverGpu = (cfg && cfg.gpu) || "";
        const storedGpu = localStorage.getItem("comfymodal_gpu") || "";
        const defaultGpu = (cfg && cfg.default_gpu) || "rtx-pro-6000";
        // The server-reported GPU wins when it is in the catalog. An unknown
        // server value must not be assigned to the select: that produces the
        // browser's blank selection and falsely looks like missing state.
        const selected = serverGpu && values.has(serverGpu)
          ? serverGpu
          : !serverGpu && storedGpu && values.has(storedGpu)
            ? storedGpu
            : values.has(defaultGpu)
              ? defaultGpu
              : options.length
                ? options[0].value
                : "rtx-pro-6000";
        while (gpuSelect.firstChild) gpuSelect.removeChild(gpuSelect.firstChild);
        if (options.length === 0) {
          gpuSelect.appendChild(el("option", { value: "rtx-pro-6000", text: "rtx-pro-6000 (default)" }));
        } else {
          options.forEach((o) => {
            gpuSelect.appendChild(el("option", { value: o.value, text: o.label || o.value }));
          });
        }
        gpuSelect.value = selected;
        if (gpuStatus) {
          if (serverGpu && !values.has(serverGpu)) {
            gpuStatus.textContent = options.length === 0
              ? "GPU options are unavailable. Showing the default without changing the server value (reported: " + serverGpu + ")."
              : "Server reports " + serverGpu + ", which is not available here. Showing " + selected + "; choose a GPU to save a change.";
            gpuStatus.style.display = "block";
          } else {
            gpuStatus.textContent = "";
            gpuStatus.style.display = "none";
          }
        }
      })
      .catch(() => {
        // Keep a truthful, usable value when the catalog is unreachable
        // instead of stranding the "Loading…" placeholder.
        if (!gpuSelect.options.length || (gpuSelect.options.length === 1 && !gpuSelect.value)) {
          while (gpuSelect.firstChild) gpuSelect.removeChild(gpuSelect.firstChild);
          gpuSelect.appendChild(el("option", { value: "rtx-pro-6000", text: "rtx-pro-6000 (default)" }));
          gpuSelect.value = "rtx-pro-6000";
        }
      });

    gpuSelect.addEventListener("change", async () => {
      const gpu = gpuSelect.value;
      try { localStorage.setItem("comfymodal_gpu", gpu); } catch (_) {}
      try {
        const resp = await fetch(base + "/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gpu: gpu }),
        });
        if (!resp.ok) throw new Error("GPU setting rejected");
        publishStudioSync("settings");
      } catch (_) {}
    });
  }

  // ΓöÇΓöÇ Deploy state refresh (state/message only) ΓöÇΓöÇ
  function refreshDeployStatus(base) {
    const row = sectionsHost.querySelector('[data-testid="settings-deploy-state"]');
    if (!row) return;
    fetch(base + "/deploy/status")
      .then((r) => r.json())
      .then((data) => {
        const state = (data && data.state) || "Unknown";
        const message = (data && data.message) || "";
        row.textContent = state + (message ? " \u2014 " + message : "");
      })
      .catch(() => { row.textContent = "Unknown"; });
  }

  // ΓöÇΓöÇ Outputs refresh (through studio-output-preferences.js) ΓöÇΓöÇ
  function refreshOutputsPrefs(base) {
    const host = sectionsHost.querySelector('[data-testid="settings-outputs-host"]');
    if (!host) return;

    loadOutputPrefsModule()
      .then(function (m) {
        return m.syncOutputConfigFromServer().then(function () {
          while (host.firstChild) host.removeChild(host.firstChild);
          const prefs = m.getOutputPreferences();
          const preview = prefs;

          const generationDefault = sectionsHost.querySelector('[data-testid="settings-preview-default"]');
          if (generationDefault) generationDefault.value = preview.preview_default;

          // Format
          const formatSelect = selectWithOptions([
            ["original", "Original"],
            ["webp_lossless", "WebP lossless"],
            ["webp_lossy", "WebP lossy"],
            ["jpeg", "JPEG"],
          ], "settings-output-format");
          formatSelect.value = prefs.output_format;
          formatSelect.addEventListener("change", () => {
            m.setOutputPreferences({ output_format: formatSelect.value }).catch(() => {
              formatSelect.value = prefs.output_format;
            });
          });
          host.appendChild(controlRow("Format", formatSelect, "Output format for generated images.", "output format"));

          // Quality (range)
          const qualityInput = el("input", {
            type: "range",
            min: "0",
            max: "100",
            step: "1",
            value: String(prefs.quality),
            class: "comfymodal-settings-range",
            "data-testid": "settings-quality",
            "aria-label": "Output quality",
          });
          const qualityVal = el("span", {
            class: "comfymodal-settings-range-value",
            "data-testid": "settings-quality-value",
            text: String(prefs.quality),
          });
          qualityInput.addEventListener("input", () => { qualityVal.textContent = qualityInput.value; });
          qualityInput.addEventListener("change", () => {
            m.setOutputPreferences({ quality: parseInt(qualityInput.value, 10) || 0 }).catch(() => {
              qualityInput.value = String(prefs.quality);
              qualityVal.textContent = String(prefs.quality);
            });
          });
          host.appendChild(controlRow("Quality", el("div", { class: "comfymodal-settings-range-wrap" }, [qualityInput, qualityVal]), "Compression quality for generated outputs (0-100).", "quality compression"));

          // WebP lossless compression
          const webpLc = selectWithOptions([
            ["fast", "Fast"],
            ["balanced", "Balanced"],
            ["max", "Maximum"],
          ], "settings-webp-lossless-compression");
          webpLc.value = prefs.webp_lossless_compression;
          webpLc.addEventListener("change", () => {
            m.setOutputPreferences({ webp_lossless_compression: webpLc.value }).catch(() => {
              webpLc.value = prefs.webp_lossless_compression;
            });
          });
          host.appendChild(controlRow("WebP lossless compression", webpLc, "Compression effort for lossless WebP outputs.", "webp lossless"));

          // Auto-save original outputs locally
          const autoSave = el("input", {
            type: "checkbox",
            checked: prefs.auto_save_local,
            class: "comfymodal-settings-checkbox",
            "data-testid": "settings-auto-save-local",
            "aria-label": "Auto-save original outputs locally",
          });
          autoSave.addEventListener("change", () => {
            m.setOutputPreferences({ auto_save_local: autoSave.checked }).catch(() => {
              autoSave.checked = !autoSave.checked;
            });
          });
          host.appendChild(controlRow("Auto-save original outputs locally", autoSave, "Copy original outputs to the local save folder.", "auto save local"));

          // Save folder
          const folderInput = el("input", {
            type: "text",
            class: "comfymodal-input",
            value: prefs.save_folder,
            "data-testid": "settings-save-folder",
            placeholder: "output/modal",
          });
          folderInput.style.cssText = "width:100%;font-size:11px;padding:3px 6px;box-sizing:border-box;";
          folderInput.addEventListener("change", () => {
            const normalized = m.normalizeOutputSaveFolder(folderInput.value);
            folderInput.value = normalized;
            m.setOutputPreferences({ save_folder: normalized }).catch(() => {
              folderInput.value = prefs.save_folder;
            });
          });
          host.appendChild(controlRow("Save folder", folderInput, "Folder where saved outputs are written (relative to the ComfyUI output dir).", "save folder"));

          // Metadata sidecar
          const sidecar = el("input", {
            type: "checkbox",
            checked: prefs.save_metadata_sidecar,
            class: "comfymodal-settings-checkbox",
            "data-testid": "settings-save-metadata-sidecar",
            "aria-label": "Save metadata JSON sidecar",
          });
          sidecar.addEventListener("change", () => {
            m.setOutputPreferences({ save_metadata_sidecar: sidecar.checked }).catch(() => {
              sidecar.checked = !sidecar.checked;
            });
          });
          host.appendChild(controlRow("Save metadata JSON sidecar", sidecar, "Write a JSON sidecar file with generation metadata.", "metadata sidecar json"));

          // Open output folder
          const openFolderBtn = el("button", {
            type: "button",
            class: "comfymodal-secondary-btn comfymodal-settings-open-folder",
            "data-testid": "settings-open-folder",
            text: "Open output folder",
          });
          openFolderBtn.addEventListener("click", () => {
            const folder = m.normalizeOutputSaveFolder(m.getOutputPreferences().save_folder);
            try {
              fetch(base + "/open-folder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: folder }),
              });
            } catch (_) {}
          });
          host.appendChild(el("div", { class: "comfymodal-settings-control", "data-search": "open output folder" }, [openFolderBtn]));

          // Keyed window listener: remove the previous handler before
          // attaching a new one so repeated renders do not accumulate.
          if (_outputPrefsListener) {
            window.removeEventListener("comfymodal:output-preferences-changed", _outputPrefsListener);
          }
          _outputPrefsListener = function () {
            const fresh = m.getOutputPreferences();
            const freshPreview = fresh;
            const syncValue = (testid, apply) => {
              const node = host.querySelector('[data-testid="' + testid + '"]');
              if (node) apply(node);
            };
            syncValue("settings-output-format", (n) => { n.value = fresh.output_format; });
            syncValue("settings-quality", (n) => { n.value = String(fresh.quality); });
            syncValue("settings-quality-value", (n) => { n.textContent = String(fresh.quality); });
            syncValue("settings-webp-lossless-compression", (n) => { n.value = fresh.webp_lossless_compression; });
            syncValue("settings-auto-save-local", (n) => { n.checked = fresh.auto_save_local; });
            syncValue("settings-save-folder", (n) => { n.value = fresh.save_folder; });
            syncValue("settings-save-metadata-sidecar", (n) => { n.checked = fresh.save_metadata_sidecar; });
             syncValue("settings-preview-default", (n) => { n.value = freshPreview.preview_default; });
             syncValue("settings-preview-codec", (n) => { n.value = freshPreview.preview_codec; });
             syncValue("settings-preview-quality", (n) => { n.value = String(freshPreview.preview_quality); });
             syncValue("settings-preview-quality-value", (n) => { n.textContent = String(freshPreview.preview_quality); });
          };
          window.addEventListener("comfymodal:output-preferences-changed", _outputPrefsListener);
          // The outputs rows are added asynchronously, after the initial
          // applyFilter() pass that already hid this section for having no
          // [data-search] units. Re-filter so the section is revealed (and
          // respects any active query).
          applyFilter();
        });
      })
      .catch(function () {
        host.appendChild(el("p", { class: "comfymodal-studio-settings-hint", text: "Output preferences unavailable." }));
        applyFilter();
      });
  }

  // ΓöÇΓöÇ Heavy tracing level refresh (server-backed) ΓöÇΓöÇ
  // Restart-banner truth model: the banner answers "has the user selected/
  // persisted a value that differs from what the current process is
  // executing?" Both sides come from GET /profile/level ({level: persisted,
  // effective}). The browser-stored selection never participates, so a stale
  // or missing localStorage default can no longer produce a false
  // "requires restart" banner while persisted == effective.
  function refreshProfileLevel(base) {
    const tracingSelect = sectionsHost.querySelector('[data-testid="settings-heavy-tracing"]');
    let userEdited = false;

    function updateBanner() {
      const pendingRestart = persistedTracingLevel !== null
        && effectiveTracingLevel !== null
        && persistedTracingLevel !== effectiveTracingLevel;
      bannerEl.style.display = pendingRestart ? "flex" : "none";
    }

    function applyServerState(data) {
      const persisted = data && typeof data.level === "string" && data.level ? data.level : "off";
      const effective = data && typeof data.effective === "string" && data.effective ? data.effective : persisted;
      persistedTracingLevel = persisted;
      effectiveTracingLevel = effective;
      // Display server truth in the select unless the user is mid-edit; the
      // localStorage key stays a user-selection cache and is not rewritten.
      if (tracingSelect && !userEdited && HEAVY_TRACING_LEVELS.indexOf(persisted) !== -1) {
        tracingSelect.value = persisted;
      }
      updateBanner();
    }

    function fetchProfileLevel() {
      fetch(base + "/profile/level")
        .then((r) => r.json())
        .then(applyServerState)
        .catch(() => { updateBanner(); });
    }

    if (tracingSelect) {
      const stored = localStorage.getItem("comfymodal_heavy_tracing") || "off";
      tracingSelect.value = HEAVY_TRACING_LEVELS.indexOf(stored) !== -1 ? stored : "off";
      tracingSelect.addEventListener("change", async () => {
        userEdited = true;
        const prev = localStorage.getItem("comfymodal_heavy_tracing") || "off";
        const level = tracingSelect.value;
        try { localStorage.setItem("comfymodal_heavy_tracing", level); } catch (_) {}
        try {
          const resp = await fetch(base + "/profile/level", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ level: level }),
          });
          if (!resp.ok) throw new Error("profile level rejected");
          publishStudioSync("settings");
        } catch (_) {
          tracingSelect.value = prev;
          try { localStorage.setItem("comfymodal_heavy_tracing", prev); } catch (e2) {}
        }
        // Re-read server truth after the attempt so the banner reflects the
        // authoritative persisted-vs-effective pair, not local guesses.
        fetchProfileLevel();
      });
    }

    fetchProfileLevel();
  }

  // Golden profiles are a server catalog, never a browser-authored list. The
  // browser may remember only the selected name; resources and deployment
  // metadata remain server truth and are deliberately not persisted.
  // GPU option labels and the active order map ride the /config fetch so the
  // GPU order controls render from the same server truth (cached at module
  // scope so re-renders after region/GPU edits keep them without refetch).
  let goldenGpuOptions = [];
  let goldenGpuOrderMap = {};
  function refreshGoldenProfiles(base) {
    const host = sectionsHost.querySelector('[data-testid="settings-golden-profile-host"]');
    if (!host) return;
    goldenDeployGeneration += 1;
    activeGoldenDeployPoll = null;
    while (host.firstChild) host.removeChild(host.firstChild);
    host.appendChild(el("p", {
      class: "comfymodal-studio-settings-hint",
      text: "Loading Golden profiles...",
    }));

    Promise.all([
      fetch(base + "/studio/golden/profiles").then(async (response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        const data = await response.json();
        if (!data || data.status !== "ok" || !Array.isArray(data.profiles)) {
          throw new Error((data && (data.message || data.error)) || "invalid catalog response");
        }
        return data;
      }),
      fetch(base + "/config").then(async (response) => {
        if (!response.ok) return {};
        return response.json();
      }).catch(() => ({})),
    ]).then(async ([catalog, config]) => {
      if (!host.isConnected) return;
      goldenProfiles = catalog.profiles.filter((profile) => profile && typeof profile.name === "string" && profile.name);
      goldenProfilesError = null;
      goldenGpuOptions = Array.isArray(config && config.available_gpus)
        ? config.available_gpus.filter((o) => o && typeof o.value === "string" && o.value)
        : [];
      goldenGpuOrderMap = (config && typeof config.golden_gpu_order === "object" && config.golden_gpu_order) || {};
      const names = new Set(goldenProfiles.map((profile) => profile.name));
      const serverSelected = config && (config.golden_profile || config.profile_name || config.profile);
      const localSelected = loadGoldenProfileSelection();
      // Prefer an explicitly persisted server/local selection, but never add
      // an option that the catalog did not return.
      const selected = names.has(serverSelected) ? serverSelected
        : names.has(localSelected) ? localSelected
          : names.has(catalog.defaultProfile) ? catalog.defaultProfile : "";
      if (selected) saveGoldenProfileSelection(selected);
      const deployState = selected
        ? await getGoldenProfileDeployStatus(base, selected)
        : null;
      if (!host.isConnected) return;
      renderGoldenProfileHost(host, base, selected, deployState);
    }).catch((error) => {
      if (!host.isConnected) return;
      goldenProfiles = [];
      goldenProfilesError = error && error.message ? error.message : "unknown catalog error";
      while (host.firstChild) host.removeChild(host.firstChild);
      host.appendChild(el("p", {
        class: "comfymodal-studio-settings-error",
        "data-testid": "settings-golden-profile-error",
        text: "Could not load Golden profiles: " + goldenProfilesError,
      }));
    });
  }

  function refreshFromWorkspaceChange() {
    if (!container.isConnected) {
      if (_workspaceChangedCleanup) _workspaceChangedCleanup();
      return;
    }
    refreshGoldenProfiles(apiBase);
  }

  // Activation is a browser event for same-tab mounts and a Studio sync
  // message for other tabs. Both paths re-read the server-owned catalog.
  const workspaceChangedListener = refreshFromWorkspaceChange;
  const hasWindow = typeof window !== "undefined";
  if (hasWindow) window.addEventListener("workspace-changed", workspaceChangedListener);
  const unsubscribeWorkspaceSync = subscribeStudioSync("workspace", refreshFromWorkspaceChange);
  _workspaceChangedCleanup = function cleanupWorkspaceChanged() {
    if (hasWindow) window.removeEventListener("workspace-changed", workspaceChangedListener);
    unsubscribeWorkspaceSync();
    if (_workspaceChangedCleanup === cleanupWorkspaceChanged) _workspaceChangedCleanup = null;
  };

  function startGoldenDeployPoll(base, name, status, button, host) {
    if (activeGoldenDeployPoll
        && activeGoldenDeployPoll.name === name
        && activeGoldenDeployPoll.owner === goldenDeployPageOwner
        && activeGoldenDeployPoll.generation === goldenDeployGeneration) {
      return activeGoldenDeployPoll.promise;
    }
    const generation = goldenDeployGeneration;
    const promise = pollGoldenDeploy(base, name, status, button, host, generation);
    activeGoldenDeployPoll = {
      name: name,
      owner: goldenDeployPageOwner,
      generation: generation,
      promise: promise,
    };
    promise.then(() => {
      if (activeGoldenDeployPoll && activeGoldenDeployPoll.promise === promise) activeGoldenDeployPoll = null;
    }, () => {
      if (activeGoldenDeployPoll && activeGoldenDeployPoll.promise === promise) activeGoldenDeployPoll = null;
    });
    return promise;
  }

  async function pollGoldenDeploy(base, name, status, button, host, generation) {
    for (let attempt = 0; attempt < 900; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      if (_goldenDeployPageOwner !== goldenDeployPageOwner
          || generation !== goldenDeployGeneration
          || !host.isConnected) return;
      const payload = await getGoldenProfileDeployStatus(base, name);
      if (_goldenDeployPageOwner !== goldenDeployPageOwner
          || generation !== goldenDeployGeneration
          || !host.isConnected) return;
      if (payload && payload.state === "done") {
        status.textContent = "Deploy finished.";
        button.disabled = false;
        refreshGoldenProfiles(base);
        return;
      }
      if (payload && payload.state === "failed") {
        const tail = deployFailureTail(payload.output || "");
        status.textContent = "Deploy failed: " + (tail || "see v2ctl output");
        button.disabled = false;
        return;
      }
    }
    if (_goldenDeployPageOwner === goldenDeployPageOwner
        && generation === goldenDeployGeneration
        && host.isConnected) {
      status.textContent = "Deploy still running. Reopen Settings to check its status.";
      button.disabled = false;
    }
  }

  async function deployGoldenProfile(base, host, name, status, button) {
    button.disabled = true;
    status.textContent = "Deploying " + name + "\u2026";
    try {
      const started = await fetch(base + "/studio/golden/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: name }),
      });
      const payload = await started.json();
      if (!started.ok || payload.status !== "ok") {
        throw new Error(payload.error || "HTTP " + started.status);
      }
      await startGoldenDeployPoll(base, name, status, button, host);
    } catch (error) {
      status.textContent = "Deploy failed: " + (error.message || "request failed");
      button.disabled = false;
    }
  }

  // ── Golden GPU orders ────────────────────────────────────────────────
  // One deploy binds TWO functions (order A on the profile class, order B on
  // the alt class).  Editing the orders is deploy-baked (save marks the
  // profile undeployed; the next Deploy binds both functions at once), while
  // the ACTIVE order radio is run-time state that applies to the next run
  // with no redeploy.
  // Profile TOML may spell a GPU in any case ("H100!" vs "h100!"); option
  // values are lowercase catalog spellings, so all matching here is
  // case-insensitive and selects resolve to the canonical option value.
  function goldenGpuOptionFor(value) {
    const want = String(value || "").trim().toLowerCase();
    if (!want) return null;
    return goldenGpuOptions.find((o) => String(o.value || "").toLowerCase() === want) || null;
  }

  function goldenGpuLabel(value) {
    const found = goldenGpuOptionFor(value);
    return (found && (found.label || found.value)) || String(value || "") || "—";
  }

  function goldenGpuOrderText(order) {
    return (Array.isArray(order) ? order : [])
      .map((value) => goldenGpuLabel(value))
      .join(" → ") || "—";
  }

  function goldenGpuSelect(current, allowEmpty, testid, ariaLabel) {
    const select = el("select", {
      class: "comfymodal-input",
      "data-testid": testid,
      "aria-label": ariaLabel,
    });
    select.style.cssText = "width:100%;font-size:11px;padding:3px 6px;";
    if (allowEmpty) {
      select.appendChild(el("option", { value: "", text: "None" }));
    }
    goldenGpuOptions.forEach((o) => {
      select.appendChild(el("option", { value: o.value, text: o.label || o.value }));
    });
    const matched = goldenGpuOptionFor(current);
    if (matched) {
      select.value = matched.value;
    } else if (!allowEmpty && goldenGpuOptions.length) {
      select.value = select.options[0].value;
    }
    return select;
  }

  function renderGoldenGpuOrders(host, base, selectedProfile) {
    const wrap = el("div", {
      class: "comfymodal-settings-control",
      "data-search": "golden profile gpu graphics card fallback order active",
      style: "display:flex;flex-direction:column;gap:6px;width:100%;margin-top:2px;",
    });
    const resources = (selectedProfile.resources && typeof selectedProfile.resources === "object")
      ? selectedProfile.resources
      : {};
    const orderA = Array.isArray(selectedProfile.gpu_order_a) ? selectedProfile.gpu_order_a : [];
    const orderB = Array.isArray(selectedProfile.gpu_order_b) ? selectedProfile.gpu_order_b : [];
    const active = goldenGpuOrderMap[selectedProfile.name] === "B" && orderB.length ? "B" : "A";

    const summaryA = el("p", {
      class: "comfymodal-studio-settings-hint",
      "data-testid": "settings-golden-profile-gpu-order-a",
      text: "",
      style: "margin:0;",
    });
    wrap.appendChild(summaryA);
    let summaryB = null;
    if (orderB.length) {
      summaryB = el("p", {
        class: "comfymodal-studio-settings-hint",
        "data-testid": "settings-golden-profile-gpu-order-b",
        text: "",
        style: "margin:0;",
      });
      wrap.appendChild(summaryB);
    }
    // The radio swaps the ACTIVE function; the stored orders below never
    // change on swap.  Repaint the summaries immediately so the swap is
    // visible without waiting for a catalog refresh.
    let shownActive = active;
    const paintActive = () => {
      summaryA.textContent = (shownActive === "B" ? "\u25CB Order A: " : "\u25CF Order A (active): ")
        + goldenGpuOrderText(orderA);
      summaryA.style.opacity = shownActive === "B" ? "0.65" : "1";
      if (summaryB) {
        summaryB.textContent = (shownActive === "B" ? "\u25CF Order B (active): " : "\u25CB Order B: ")
          + goldenGpuOrderText(orderB);
        summaryB.style.opacity = shownActive === "B" ? "1" : "0.65";
      }
    };
    paintActive();

    // Active order: run-time swap, no redeploy.
    const activeRow = el("div", { style: "display:flex;align-items:center;gap:12px;" });
    const radioName = "golden-gpu-active-" + selectedProfile.name;
    const radioA = el("input", {
      type: "radio", name: radioName, value: "A",
      "data-testid": "settings-golden-profile-gpu-active-a",
      "aria-label": "Use GPU order A",
    });
    const radioB = el("input", {
      type: "radio", name: radioName, value: "B",
      "data-testid": "settings-golden-profile-gpu-active-b",
      "aria-label": "Use GPU order B",
    });
    radioA.checked = active !== "B";
    radioB.checked = active === "B";
    if (!orderB.length) radioB.disabled = true;
    const orderError = el("p", {
      class: "comfymodal-studio-settings-hint",
      "data-testid": "settings-golden-profile-gpu-order-error",
      text: "",
      style: "margin:0;",
    });
    const applyActive = async (wanted) => {
      orderError.textContent = "";
      radioA.disabled = true;
      radioB.disabled = true;
      try {
        const response = await setGoldenProfileGpuOrder(base, selectedProfile.name, wanted);
        if (!response || response.status !== "ok") {
          throw new Error((response && (response.error || response.message)) || "request failed");
        }
        goldenGpuOrderMap[selectedProfile.name] = wanted;
        shownActive = wanted;
        paintActive();
        publishStudioSync("settings");
        orderError.textContent = wanted === "B"
          ? "Order B is active. Applies to the next run — no redeploy."
          : "Order A is active. Applies to the next run — no redeploy.";
      } catch (error) {
        radioA.checked = shownActive !== "B";
        radioB.checked = shownActive === "B";
        orderError.textContent = "Could not switch GPU order: " + (error.message || "request failed");
      } finally {
        radioA.disabled = false;
        radioB.disabled = !orderB.length;
      }
    };
    radioA.addEventListener("change", () => { if (radioA.checked) applyActive("A"); });
    radioB.addEventListener("change", () => { if (radioB.checked) applyActive("B"); });
    activeRow.appendChild(el("label", {}, ["Order A ", radioA]));
    activeRow.appendChild(el("label", {}, ["Order B ", radioB]));
    if (!orderB.length) {
      activeRow.appendChild(el("span", {
        class: "comfymodal-studio-settings-hint",
        text: "No order B configured.",
      }));
    }
    wrap.appendChild(activeRow);
    wrap.appendChild(orderError);

    // Order editor: deploy-baked, saved to the profile TOML.  These are the
    // STORED orders, not a view of the active one, so swapping the radio
    // above never rewrites them.
    const editor = el("div", { style: "display:flex;flex-direction:column;gap:6px;width:100%;" });
    editor.appendChild(el("div", {
      class: "comfymodal-studio-settings-hint",
      text: "Stored orders (editing + Save marks the profile undeployed):",
    }));
    const primaryA = goldenGpuSelect(resources.gpu || (orderA[0] || ""), false,
      "settings-golden-profile-gpu-primary-a", "Order A primary GPU");
    editor.appendChild(el("div", { class: "comfymodal-studio-settings-hint", style: "margin:0;display:flex;align-items:center;gap:8px;" },
      [el("label", {}, ["Primary A ", primaryA])]));
    const primaryB = goldenGpuSelect(resources.gpu_alt || "", true,
      "settings-golden-profile-gpu-primary-b", "Order B primary GPU (empty for a single function)");
    editor.appendChild(el("div", { class: "comfymodal-studio-settings-hint", style: "margin:0;display:flex;align-items:center;gap:8px;" },
      [el("label", {}, ["Primary B ", primaryB])]));
    const storedFallbacks = Array.isArray(resources.gpu_fallbacks) ? resources.gpu_fallbacks : [];
    const fallbackSelects = [];
    for (let index = 0; index < 4; index += 1) {
      const select = goldenGpuSelect(storedFallbacks[index] || "", true,
        "settings-golden-profile-gpu-fallback-" + index, "Shared fallback " + (index + 1));
      fallbackSelects.push(select);
      editor.appendChild(el("div", { class: "comfymodal-studio-settings-hint", style: "margin:0;display:flex;align-items:center;gap:8px;" },
        [el("label", {}, ["Fallback " + (index + 1) + " ", select])]));
    }
    const gpuError = el("p", {
      class: "comfymodal-studio-settings-hint",
      "data-testid": "settings-golden-profile-gpu-error",
      text: "",
      style: "margin:0;",
    });
    const saveButton = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn",
      "data-testid": "settings-golden-profile-gpu-save",
      text: "Save GPU orders",
      title: "Save GPU orders to the profile (marks undeployed; deploy binds both functions)",
    });
    saveButton.addEventListener("click", async () => {
      gpuError.textContent = "";
      saveButton.disabled = true;
      try {
        const response = await setGoldenProfileGpu(
          base,
          selectedProfile.name,
          primaryA.value,
          primaryB.value,
          fallbackSelects.map((select) => select.value).filter((value) => value),
        );
        if (!response || response.status !== "ok") {
          throw new Error((response && (response.error || response.message)) || "request failed");
        }
        publishStudioSync("settings");
        // Re-read the catalog so deploy state and derived orders are exact,
        // not optimistic: new orders change the deploy fingerprint.
        refreshGoldenProfiles(base);
      } catch (error) {
        gpuError.textContent = "Could not save GPU orders: " + (error.message || "request failed");
        saveButton.disabled = false;
      }
    });
    const saveRow = el("div", { style: "display:flex;align-items:center;gap:8px;" }, [saveButton]);
    editor.appendChild(saveRow);
    editor.appendChild(gpuError);
    editor.appendChild(el("div", {
      class: "comfymodal-studio-settings-hint",
      text: "GPU orders are deploy-baked: saving marks the profile undeployed, and the next Deploy binds both functions at once. Switching the active order above never redeploys.",
    }));
    wrap.appendChild(editor);
    host.appendChild(wrap);
  }

  function renderGoldenProfileHost(host, base, selected, deployState) {
    if (activeGoldenDeployPoll && activeGoldenDeployPoll.name !== selected) {
      goldenDeployGeneration += 1;
      activeGoldenDeployPoll = null;
    }
    while (host.firstChild) host.removeChild(host.firstChild);
    if (goldenProfilesError) {
      host.appendChild(el("p", {
        class: "comfymodal-studio-settings-error",
        "data-testid": "settings-golden-profile-error",
        text: "Could not load Golden profiles: " + goldenProfilesError,
      }));
      return;
    }
    const select = el("select", {
      class: "comfymodal-input",
      "data-testid": "settings-golden-profile",
      "aria-label": "Golden execution profile",
    });
    if (goldenProfiles.length === 0) {
      select.appendChild(el("option", { value: "", text: "No Golden profiles available", disabled: true, selected: true }));
      select.disabled = true;
    } else {
      goldenProfiles.forEach((profile) => {
        const deployed = profile.deployed === true;
        const option = el("option", {
          value: profile.name,
          text: profile.name + (deployed ? " (deployed)" : " (undeployed ΓÇö deploy before use)"),
        });
        // An undeployed profile is a normal, selectable state: the user picks it
        // and then deploys it. Disabling the option made that impossible.
        if (favoriteProfileNames().has(profile.name)) {
          option.text = "\u2605 " + option.text;
        }
        if (profile.name === selected) option.selected = true;
        select.appendChild(option);
      });
      select.value = selected || "";
    }
    select.addEventListener("change", async () => {
      const profile = goldenProfiles.find((item) => item.name === select.value);
      if (!profile) return;
      const previous = loadGoldenProfileSelection();
      // Persist the choice either way so the Deploy control has a target, but
      // only hand a deployed profile to the backend. Selecting is not the same
      // as committing to run.
      saveGoldenProfileSelection(profile.name);
      if (profile.deployed !== true) {
        renderGoldenProfileHost(host, base, profile.name);
        return;
      }
      try {
        const response = await fetch(base + "/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ golden_profile: profile.name }),
        });
        if (!response.ok) throw new Error("HTTP " + response.status);
        saveGoldenProfileSelection(profile.name);
        publishStudioSync("settings");
      } catch (error) {
        select.value = previous || "";
        const errorEl = host.querySelector('[data-testid="settings-golden-profile-save-error"]');
        if (errorEl) errorEl.textContent = "Could not save Golden profile: " + (error.message || "request failed");
      }
    });
    const selectedProfile = goldenProfiles.find(
      (item) => item.name === (selected || "")
    );
    const isDeploying = (deployState && deployState.state === "running")
      || (activeGoldenDeployPoll
         && activeGoldenDeployPoll.name === selectedProfile?.name
         && activeGoldenDeployPoll.owner === goldenDeployPageOwner);
    const profileBar = el("div", {
      class: "comfymodal-studio-settings-golden-profile-bar",
      "data-testid": "settings-golden-profile-bar",
      style: "display:flex;align-items:center;gap:8px;width:100%;",
    }, [select]);
    if (selectedProfile) {
      const selTarget = selectedProfile.target && typeof selectedProfile.target === "object"
        ? selectedProfile.target
        : {};
      const deployStatus = el("p", {
        class: "comfymodal-studio-settings-hint",
        "data-testid": "settings-golden-profile-deploy-status",
        text: isDeploying
          ? "Deploying " + selectedProfile.name + "\u2026"
          : selectedProfile.deployed !== true
          ? selTarget.app
            ? "Not deployed. Deploying runs v2ctl for " + selectedProfile.name
              + " (" + selTarget.app + ")."
            : "Not deployed."
          : "",
      });
      const deployButton = el("button", {
        class: "comfymodal-primary-btn",
        "data-testid": "settings-golden-profile-deploy",
        "data-profile-name": selectedProfile.name,
        text: selectedProfile.deployed === true ? "Redeploy" : "Deploy " + selectedProfile.name,
        title: selectedProfile.deployed === true
          ? "Redeploy the selected Golden profile"
          : "Deploy the selected Golden profile",
        disabled: !!isDeploying,
        onclick: () => deployGoldenProfile(base, host, selectedProfile.name, deployStatus, deployButton),
      });
      profileBar.appendChild(deployButton);
      const star = el("button", {
        class: "comfymodal-secondary-btn",
        "data-testid": "settings-golden-profile-favorite",
        "data-profile-name": selectedProfile.name,
        "aria-pressed": favoriteProfileNames().has(selectedProfile.name) ? "true" : "false",
        text: favoriteProfileNames().has(selectedProfile.name) ? "\u2605" : "\u2606",
        title: "Favorite this profile",
        onclick: () => {
          toggleFavoriteProfile(selectedProfile.name);
          renderGoldenProfileHost(host, base, select.value);
        },
      });
      profileBar.appendChild(star);
      host.appendChild(profileBar);
      const regionPin = el("select", {
        class: "comfymodal-input",
        "data-testid": "settings-golden-profile-region-pin",
        "aria-label": "Golden profile region pin",
      });
      [
        ["", "Provider default (unpinned)"],
        ["us", "US"],
        ["us-central", "US Central"],
      ].forEach(([value, label]) => {
        const option = el("option", { value: value, text: label });
        if ((selectedProfile.region || "") === value) option.selected = true;
        regionPin.appendChild(option);
      });
      regionPin.value = selectedProfile.region || "";
      const regionHint = el("span", {
        class: "comfymodal-studio-settings-hint",
        text: "Overwrites the profile TOML (COMFYMODAL_V2_REGION); takes effect on (re)deploy.",
      });
      const regionRow = el("div", {
        class: "comfymodal-studio-settings-hint",
        style: "display:flex;align-items:center;gap:8px;width:100%;",
      }, [
        el("label", {}, [document.createTextNode("Region pin "), regionPin]),
        regionHint,
      ]);
      regionPin.addEventListener("change", async () => {
        const previous = selectedProfile.region || "";
        regionPin.disabled = true;
        try {
          const response = await setGoldenProfileRegion(
            base,
            selectedProfile.name,
            regionPin.value,
          );
          if (!response || response.status !== "ok") {
            throw new Error((response && (response.error || response.message)) || "request failed");
          }
          // The POST already confirmed server truth, so update the in-memory
          // profile and re-render synchronously. A full refresh would force a
          // ~10s cold catalog rescan (the save invalidated the memoised
          // catalog) and blank the section meanwhile. Marking undeployed is
          // exact, not optimistic: region is a deploy-baked flag, so the
          // changed fingerprint can no longer match the previous receipt.
          selectedProfile.region = regionPin.value;
          selectedProfile.deployed = false;
          renderGoldenProfileHost(host, base, select.value, deployState);
        } catch (error) {
          regionPin.value = previous;
          const errorEl = host.querySelector('[data-testid="settings-golden-profile-save-error"]');
          if (errorEl) {
            errorEl.textContent = "Could not save Golden profile region: "
              + (error.message || "request failed");
          }
          regionPin.disabled = false;
        }
      });
      host.appendChild(regionRow);
      renderGoldenGpuOrders(host, base, selectedProfile);
      host.appendChild(deployStatus);
      if (isDeploying) {
        startGoldenDeployPoll(base, selectedProfile.name, deployStatus, deployButton, host).catch((error) => {
          if (_goldenDeployPageOwner !== goldenDeployPageOwner || !host.isConnected) return;
          deployStatus.textContent = "Deploy failed: " + (error.message || "request failed");
          deployButton.disabled = false;
        });
      }
    } else {
      host.appendChild(profileBar);
    }

    host.appendChild(el("p", {
      class: "comfymodal-studio-settings-hint",
      "data-testid": "settings-golden-profile-save-error",
      text: "",
    }));
  }

  // Initial build
  rebuildPage();
  return container;
}
