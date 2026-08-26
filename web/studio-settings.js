// Modal Studio — Settings
//
// Seven-section settings page: General, Generation, Outputs, History,
// Experiments, Interface, Advanced. Preferences-only (H5 §2); the former
// Settings ▸ Advanced ▸ Legacy group and legacy-tab embedding were retired
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

// ── Constants ────────────────────────────────────────────────────────────

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

// Keys managed by the modern Settings page. "Reset all settings" clears
// exactly this set — nothing under comfymodal.studio.playground.* or the
// other user-data namespaces is touched.
//
// Guard: every key here must be classified with real reader/writer evidence
// in tests/studio_phase_f4_settings_authority_unit.mjs. Reset-only keys with
// no consumer fail that registry-equality check; removed stale keys must not
// reappear anywhere in this file.
//
// H12: the canvas Cloud/Local run-mode key left this registry — it has zero
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
  "comfymodal-studio-history-columns",
  "comfymodal_heavy_tracing",
  "comfymodal-studio-panel-width",
  "comfymodal.studio.playground.carousel-cleared.v1",
];

const HEAVY_TRACING_LEVELS = ["off", "summary", "detailed", "trace", "trace_verbose"];

// Stable listener handles. The shell re-creates all page DOM on every page
// switch, so element-keyed handlers cannot survive a re-render; tracking
// the last-attached handler at module scope lets us remove it before
// attaching the new one — fixing the per-render window listener leak.
let _outputPrefsListener = null;

let _outputPrefsModulePromise = null;
function loadOutputPrefsModule() {
  if (!_outputPrefsModulePromise) {
    _outputPrefsModulePromise = import("./studio-output-preferences.js");
  }
  return _outputPrefsModulePromise;
}

// ── Element helper ───────────────────────────────────────────────────────

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

// ── Preview preference helpers ────────────────────────────────────────────

function getPreviewPrefs() {
  return {
    preview_default: localStorage.getItem("comfymodal_preview_default") === "on"
      ? "on" : PREVIEW_DEFAULTS.preview_default,
    preview_codec: localStorage.getItem("comfymodal_preview_codec") === "webp"
      ? "webp" : PREVIEW_DEFAULTS.preview_codec,
    preview_quality: parseInt(localStorage.getItem("comfymodal_preview_quality"), 10) || PREVIEW_DEFAULTS.preview_quality,
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

// ── Shared row builders ──────────────────────────────────────────────────

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

// ── renderSettings (public) ──────────────────────────────────────────────

export function renderSettings(state, context) {
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

  // Truthful page h2 under the shell h1 (I1 §3.3 / I7). Settings has no
  // visible page title, so the heading is accessible-but-visually-hidden
  // with the clip pattern — never display:none / visibility:hidden.
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

  // ── Pending-restart banner (persistent across rebuilds) ──
  const bannerEl = el("div", {
    class: "comfymodal-settings-restart-banner",
    "data-testid": "settings-restart-banner",
    style: "display:none;",
  });
  bannerEl.textContent = "Heavy tracing change requires a ComfyUI restart to take effect.";
  container.appendChild(bannerEl);

  // ── Search ──
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
  const searchWrap = el("div", { class: "comfymodal-settings-search-wrap" }, [searchInput, searchResultEl]);
  container.appendChild(searchWrap);

  const sectionsHost = el("div", { class: "comfymodal-settings-sections" });
  container.appendChild(sectionsHost);

  const footerEl = el("div", { class: "comfymodal-settings-footer" });
  container.appendChild(footerEl);

  // ── Search filter (state is local to this render) ──
  function applyFilter() {
    const q = (searchInput.value || "").trim().toLowerCase();
    let matched = 0;
    sectionsHost.querySelectorAll("[data-search]").forEach((unit) => {
      const hit = !q || (unit.dataset.search || "").indexOf(q) !== -1;
      unit.classList.toggle("comfymodal-settings-row-hidden", !hit);
      if (hit) matched++;
    });
    sectionsHost.querySelectorAll(".comfymodal-studio-settings-section").forEach((section) => {
      const anyVisible = section.querySelectorAll(
        "[data-search]:not(.comfymodal-settings-row-hidden)"
      ).length > 0;
      section.style.display = anyVisible ? "" : "none";
    });
    if (q) {
      searchResultEl.textContent = matched === 0
        ? "No settings match your search"
        : matched + " matching setting" + (matched === 1 ? "" : "s");
      searchResultEl.style.display = "block";
    } else {
      searchResultEl.textContent = "";
      searchResultEl.style.display = "none";
    }
  }

  searchInput.addEventListener("input", applyFilter);

  // ── Helpers used by resets ──
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

  // ── Per-section reset implementations ──
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
      removeKeys(["comfymodal_gpu", "comfymodal_preview_default"]);
      try {
        const m = await loadOutputPrefsModule();
        await m.setOutputPreferences({ preview_default: PREVIEW_DEFAULTS.preview_default });
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
    },
    outputs: async () => {
      removeKeys([
        "comfymodal_output_format",
        "comfymodal_quality",
        "comfymodal_webp_lossless_compression",
        "comfymodal_auto_save_local",
        "comfymodal_save_folder",
        "comfymodal_save_metadata_sidecar",
        "comfymodal_preview_codec",
        "comfymodal_preview_quality",
      ]);
      try {
        const m = await loadOutputPrefsModule();
        await m.setOutputPreferences(Object.assign({}, OUTPUT_DEFAULTS));
      } catch (_) {}
      syncWindowOutputOptions();
    },
    history: async () => {
      removeKeys(["comfymodal-studio-history-columns"]);
    },
    interface: async () => {
      removeKeys(["comfymodal-studio-panel-width", "comfymodal.studio.playground.carousel-cleared.v1"]);
    },
    advanced: async () => {
      removeKeys(["comfymodal_heavy_tracing"]);
      try {
        await fetch(apiBase + "/profile/level", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ level: "off" }),
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
      "Reset all Studio settings (General, Generation, Outputs, History, Experiments, Interface, Advanced) to defaults. " +
      "The GPU selection is reset to the default. " +
      "Your Workflows, run History, snapshots, presets, drafts, and assets are NOT affected."
    );
    if (!ok) return;
    removeKeys(MODERN_SETTINGS_KEYS);
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
      await fetch(apiBase + "/profile/level", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: "off" }),
      });
    } catch (_) {}
    publishStudioSync("settings");
    rebuildPage();
    const confirmEl = el("span", { class: "comfymodal-settings-reset-confirm", text: "All settings reset to defaults" });
    footerEl.appendChild(confirmEl);
    setTimeout(() => { if (confirmEl.parentNode) confirmEl.parentNode.removeChild(confirmEl); }, 2600);
  }

  // ── Section builders ───────────────────────────────────────────────────

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

  // ── 1. General ──
  function buildGeneralSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "general" });
    // H12: the Cloud/Local Run mode control is retired — it had zero modern
    // Studio consumers and gated only legacy canvas /prompt interception.
    // The canvas compatibility layer keeps its own key; nothing here resets
    // or writes it. Nothing in General is resettable → no reset button.
    section.appendChild(buildSectionHeader("General", ""));
    section.appendChild(infoRow("Primary navigation: Playground / History / Workflows / Backend / Settings."));
    return section;
  }

  // ── 2. Generation ──
  function buildGenerationSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "generation" });
    section.appendChild(buildSectionHeader("Generation", "settings-reset-generation"));

    // H12: the V1/V2 Execution Engine selector is retired — Modal V2 is the
    // only public Studio engine, so there is no engine choice to expose.
    // GPU remains the sole execution-affecting preference in Settings.

    // GPU (server-backed; localStorage comfymodal_gpu is a display cache only)
    const gpuSelect = el("select", { class: "comfymodal-input", "data-testid": "settings-gpu" });
    gpuSelect.style.cssText = "width:100%;font-size:11px;padding:3px 6px;";
    section.appendChild(controlRow("GPU", gpuSelect, "You only pay while generating.", "gpu graphics card"));

    // Preview default (global, server-backed)
    const previewDefault = selectWithOptions([["off", "Off"], ["on", "On"]], "settings-preview-default");
    previewDefault.value = getPreviewPrefs().preview_default;
    previewDefault.addEventListener("change", () => {
      const previous = previewDefault.value === "on" ? "off" : "on";
      setPreviewPrefs({ preview_default: previewDefault.value }).catch(() => {
        previewDefault.value = previous;
      });
    });
    section.appendChild(controlRow("Preview default", previewDefault, "Global default for result previews. Applies to new submissions only.", "preview default"));

    // One-time H12 migration notice (surfaced only when this server process
    // migrated a persisted retired engine value at startup).
    section.appendChild(el("div", { "data-testid": "settings-migration-notice-host" }));
    return section;
  }

  // ── 3. Outputs ──
  function buildOutputsSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "outputs" });
    section.appendChild(buildSectionHeader("Outputs", "settings-reset-outputs"));
    section.appendChild(el("div", { "data-testid": "settings-outputs-host" }));
    return section;
  }

  // ── 4. History ──
  function buildHistorySection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "history" });
    section.appendChild(buildSectionHeader("History", "settings-reset-history"));

    const columnsSelect = el("select", { class: "comfymodal-input", "data-testid": "settings-history-columns" });
    for (let n = 2; n <= 8; n++) {
      columnsSelect.appendChild(el("option", { value: String(n), text: String(n) }));
    }
    const savedColumns = parseInt(localStorage.getItem("comfymodal-studio-history-columns"), 10);
    columnsSelect.value = String(savedColumns >= 2 && savedColumns <= 8 ? savedColumns : 6);
    columnsSelect.addEventListener("change", () => {
      try { localStorage.setItem("comfymodal-studio-history-columns", columnsSelect.value); } catch (_) {}
    });
    section.appendChild(controlRow("Grid columns", columnsSelect, "Number of columns in the run history grid.", "history grid columns"));
    section.appendChild(infoRow("Run history is stored locally and is kept until you delete it."));
    return section;
  }

  // ── 5. Experiments ──
  function buildExperimentsSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "experiments" });
    // Informational only: concurrency is backend-fixed at 6, so there is
    // nothing to reset — no reset button is rendered.
    section.appendChild(buildSectionHeader("Experiments", ""));
    section.appendChild(infoRow("Experiments run up to 6 cells concurrently. Per-experiment overrides are not available."));
    return section;
  }

  // ── 6. Interface ──
  function buildInterfaceSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "interface" });
    section.appendChild(buildSectionHeader("Interface", "settings-reset-interface"));

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

  // ── 7. Advanced ──
  function buildAdvancedSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "advanced" });
    section.appendChild(buildSectionHeader("Advanced", "settings-reset-advanced"));

    // Heavy tracing (server-backed via /profile/level, local key for the selection)
    const tracingSelect = selectWithOptions([
      ["off", "Off"],
      ["summary", "Summary"],
      ["detailed", "Detailed"],
      ["trace", "Trace"],
      ["trace_verbose", "Trace verbose"],
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

    // Runtime & Backend group
    const runtimeGroup = el("div", {
      class: "comfymodal-settings-group",
      "data-search": "runtime backend deploy state snapshots presets",
    });
    runtimeGroup.appendChild(el("h4", { class: "comfymodal-settings-group-title", text: "Runtime & Backend" }));

    const deployWrap = el("div", { class: "comfymodal-settings-control", "data-search": "deploy state" });
    deployWrap.appendChild(settingsRow("Deploy state", el("span", {
      class: "comfymodal-studio-settings-row-value",
      "data-testid": "settings-deploy-state",
      text: "\u2014",
    })));
    runtimeGroup.appendChild(deployWrap);

    const snapWrap = el("div", { class: "comfymodal-settings-control", "data-search": "snapshots" });
    snapWrap.appendChild(settingsRow("Snapshots", el("span", {
      class: "comfymodal-studio-settings-row-value",
      "data-testid": "settings-runtime-snapshots",
      text: "\u2014",
    })));
    runtimeGroup.appendChild(snapWrap);

    const presetWrap = el("div", { class: "comfymodal-settings-control", "data-search": "presets" });
    presetWrap.appendChild(settingsRow("Presets", el("span", {
      class: "comfymodal-studio-settings-row-value",
      "data-testid": "settings-runtime-presets",
      text: "\u2014",
    })));
    runtimeGroup.appendChild(presetWrap);

    // H16 Wave F (FD-8): the legacy-compatibility count row for the retired
    // comparison store was removed here along with its fetch leg. Settings
    // owns preferences only; the remaining rows stay as recorded debt.

    const backendLinkWrap = el("div", { class: "comfymodal-settings-control", "data-search": "open backend tab" });
    const backendLink = el("a", {
      class: "comfymodal-settings-link",
      "data-testid": "settings-open-backend",
      text: "Open Backend tab",
      href: "#",
    });
    backendLink.addEventListener("click", (e) => {
      e.preventDefault();
      if (context && context.setPage) context.setPage("backend");
    });
    backendLinkWrap.appendChild(settingsRow("Backend", backendLink));
    runtimeGroup.appendChild(backendLinkWrap);
    section.appendChild(runtimeGroup);

    // H14 Wave E: the Settings ▸ Advanced ▸ Legacy group (opener +
    // Setup/Profiles/Results/Settings entries) is retired. Modern Settings
    // is preferences-only (H5 §2); no legacy tab remains mountable.

    return section;
  }

  // ── Assembly + async refreshes ─────────────────────────────────────────

  function buildSections() {
    const sections = [
      buildGeneralSection(),
      buildGenerationSection(),
      buildOutputsSection(),
      buildHistorySection(),
      buildExperimentsSection(),
      buildInterfaceSection(),
      buildAdvancedSection(),
    ];
    const footer = el("div", { class: "comfymodal-settings-footer-inner" }, [
      el("p", {
        class: "comfymodal-settings-footer-note",
        text: "Reset all Studio settings to defaults. The GPU selection resets to the default. User data (workflows, history, snapshots, presets, drafts, assets) is preserved.",
      }),
      el("button", {
        type: "button",
        class: "comfymodal-destructive-btn comfymodal-settings-reset-all-btn",
        "data-testid": "settings-reset-all",
        text: "Reset all settings",
        onclick: runResetAll,
      }),
    ]);
    return { sections: sections, footer: footer };
  }

  function rebuildPage() {
    while (sectionsHost.firstChild) sectionsHost.removeChild(sectionsHost.firstChild);
    while (footerEl.firstChild) footerEl.removeChild(footerEl.firstChild);
    const { sections, footer } = buildSections();
    for (const s of sections) sectionsHost.appendChild(s);
    footerEl.appendChild(footer);
    applyFilter();
    refreshEngineMigrationNotice(apiBase);
    refreshGpuConfig(apiBase);
    refreshDeployStatus(apiBase);
    refreshRuntimeCounts(apiBase);
    refreshOutputsPrefs(apiBase);
    refreshProfileLevel(apiBase);
  }

  // ── H12 engine migration notice (server-backed, one-time) ──
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

  // ── GPU refresh (server truth first; localStorage as cache only) ──
  function refreshGpuConfig(base) {
    const gpuSelect = sectionsHost.querySelector('[data-testid="settings-gpu"]');
    if (!gpuSelect) return;

    fetch(base + "/config")
      .then((r) => r.json())
      .then((cfg) => {
        const options = Array.isArray(cfg && cfg.available_gpus) ? cfg.available_gpus : [];
        const values = new Set(options.map((o) => o.value));
        const serverGpu = (cfg && cfg.gpu) || "";
        const storedGpu = localStorage.getItem("comfymodal_gpu") || "";
        // The server-reported GPU wins over the localStorage cache so a stale
        // browser value can never mask current server state. LS is consulted
        // only when the server reports no usable value.
        const selected = serverGpu && values.has(serverGpu)
          ? serverGpu
          : storedGpu && values.has(storedGpu)
            ? storedGpu
            : (serverGpu || (cfg && cfg.default_gpu) || "rtx-pro-6000");
        while (gpuSelect.firstChild) gpuSelect.removeChild(gpuSelect.firstChild);
        if (options.length === 0) {
          gpuSelect.appendChild(el("option", { value: "rtx-pro-6000", text: "rtx-pro-6000 (default)" }));
        } else {
          options.forEach((o) => {
            gpuSelect.appendChild(el("option", { value: o.value, text: o.label || o.value }));
          });
        }
        gpuSelect.value = selected;
      })
      .catch(() => {});

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

  // ── Deploy state refresh (state/message only) ──
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

  // ── Runtime inventory counts ──
  function refreshRuntimeCounts(base) {
    const snapEl = sectionsHost.querySelector('[data-testid="settings-runtime-snapshots"]');
    const presetEl = sectionsHost.querySelector('[data-testid="settings-runtime-presets"]');
    if (!snapEl && !presetEl) return;

    Promise.all([
      fetch(base + "/studio/snapshots").then((r) => r.json()).catch(() => ({})),
      fetch(base + "/studio/presets").then((r) => r.json()).catch(() => ({})),
    ]).then(([snapData, presetData]) => {
      if (snapEl) snapEl.textContent = String((snapData && snapData.snapshots ? snapData.snapshots.length : 0));
      if (presetEl) presetEl.textContent = String((presetData && presetData.presets ? presetData.presets.length : 0));
    });
  }

  // ── Outputs refresh (through studio-output-preferences.js) ──
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

          // Preview codec (global, server-backed)
          const previewCodec = selectWithOptions([["webp", "WebP"]], "settings-preview-codec");
          previewCodec.value = preview.preview_codec;
          previewCodec.addEventListener("change", () => {
            const previous = preview.preview_codec;
            setPreviewPrefs({ preview_codec: previewCodec.value }).catch(() => {
              previewCodec.value = previous;
            });
          });
          host.appendChild(controlRow("Preview codec", previewCodec, "Codec used for preview thumbnails.", "preview codec"));

          // Preview quality (new, local-only)
          const previewQuality = el("input", {
            type: "range",
            min: "1",
            max: "100",
            step: "1",
            value: String(preview.preview_quality),
            class: "comfymodal-settings-range",
            "data-testid": "settings-preview-quality",
            "aria-label": "Preview quality",
          });
          const previewQualityVal = el("span", {
            class: "comfymodal-settings-range-value",
            "data-testid": "settings-preview-quality-value",
            text: String(preview.preview_quality),
          });
          previewQuality.addEventListener("input", () => { previewQualityVal.textContent = previewQuality.value; });
          previewQuality.addEventListener("change", () => {
            const previous = preview.preview_quality;
            setPreviewPrefs({ preview_quality: parseInt(previewQuality.value, 10) || 70 }).catch(() => {
              previewQuality.value = String(previous);
              previewQualityVal.textContent = String(previous);
            });
          });
          host.appendChild(controlRow("Preview quality", el("div", { class: "comfymodal-settings-range-wrap" }, [previewQuality, previewQualityVal]), "Compression quality for preview thumbnails (1-100).", "preview quality"));

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
        });
      })
      .catch(function () {
        host.appendChild(el("p", { class: "comfymodal-studio-settings-hint", text: "Output preferences unavailable." }));
      });
  }

  // ── Heavy tracing level refresh (server-backed) ──
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

  // Initial build
  rebuildPage();
  return container;
}
