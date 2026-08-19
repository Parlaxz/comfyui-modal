// Modal Studio — Settings
//
// Seven-section settings page: General, Generation, Outputs, History,
// Experiments, Interface, Advanced. Legacy testing-suite tabs embed via
// renderLegacyView → context.mountLegacyTab.
//
// Contracts:
//  - Exports renderSettings(state, context) (shell PAGES.settings) and
//    renderLegacyView(state, context) (shell legacy-tab embedding).
//  - state.settings.activeLegacyTab / state.settings.activeSection behavior
//    is preserved; legacy entries set activeLegacyTab then render the
//    legacy wrapper.
//  - Each section keeps a data-section attribute so modal-testing.js can
//    scroll to [data-section=...] via comfymodal.open-section.
//  - Output preferences go through ./studio-output-preferences.js (dynamic
//    import) which dual-writes localStorage + POST /comfymodal/config and
//    keeps its failure-revert behavior.
//  - All new localStorage keys are flat strings.

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
const MODERN_SETTINGS_KEYS = [
  "comfymodal_enabled",
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
  "comfymodal_preview_auto_save",
  "comfymodal-studio-history-columns",
  "comfymodal_global_concurrency",
  "comfymodal_heavy_tracing",
  "comfymodal-studio-panel-width",
  "comfymodal.studio.playground.carousel-cleared.v1",
];

const HEAVY_TRACING_LEVELS = ["off", "summary", "detailed", "trace", "trace_verbose"];

// Stable listener handles. The shell re-creates all page DOM on every page
// switch, so element-keyed handlers cannot survive a re-render; tracking
// the last-attached handler at module scope lets us remove it before
// attaching the new one — fixing the per-render window listener leak.
let _executionModeListener = null;
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

  // If a legacy tab is active, render the legacy wrapper view
  if (state.settings.activeLegacyTab) {
    container.appendChild(renderLegacyView(state, context));
    return container;
  }

  const apiBase = (context && context.apiBase) || "/comfymodal";
  let effectiveTracingLevel = "off";

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
  const resets = {
    general: async () => {
      removeKeys(["comfymodal_enabled"]);
    },
    generation: async () => {
      removeKeys(["comfymodal_gpu", "comfymodal_preview_default"]);
      try {
        const m = await loadOutputPrefsModule();
        await m.setOutputPreferences({ preview_default: PREVIEW_DEFAULTS.preview_default });
      } catch (_) {}
      try {
        await fetch(apiBase + "/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ execution_mode: "v2" }),
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
    experiments: async () => {
      removeKeys(["comfymodal_global_concurrency"]);
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
    rebuildPage();
    showTransient("settings-reset-" + key, "Section reset to defaults");
  }

  async function runResetAll() {
    const ok = confirm(
      "Reset all Studio settings (General, Generation, Outputs, History, Experiments, Interface, Advanced) to defaults. " +
      "Your Workflows, run History, snapshots, presets, drafts, and assets are NOT affected."
    );
    if (!ok) return;
    removeKeys(MODERN_SETTINGS_KEYS);
    try {
      await fetch(apiBase + "/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execution_mode: "v2" }),
      });
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
    rebuildPage();
    const confirmEl = el("span", { class: "comfymodal-settings-reset-confirm", text: "All settings reset to defaults" });
    footerEl.appendChild(confirmEl);
    setTimeout(() => { if (confirmEl.parentNode) confirmEl.parentNode.removeChild(confirmEl); }, 2600);
  }

  // ── Section builders ───────────────────────────────────────────────────

  function buildSectionHeader(title, resetTestid) {
    const head = el("div", { class: "comfymodal-studio-settings-section-head" });
    head.appendChild(el("h3", { text: title }));
    const actions = el("div", { class: "comfymodal-settings-section-actions" });
    actions.appendChild(el("button", {
      type: "button",
      class: "comfymodal-settings-reset-section-btn",
      "data-testid": resetTestid,
      text: "Reset section",
      onclick: () => runSectionReset(resetTestid.replace("settings-reset-", "")),
    }));
    head.appendChild(actions);
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
    section.appendChild(buildSectionHeader("General", "settings-reset-general"));

    // Run mode — segmented Cloud/Local control (mirrors legacy modal-settings.js)
    const savedEnabled = localStorage.getItem("comfymodal_enabled");
    let isCloud = savedEnabled === null ? true : savedEnabled === "true";

    const seg = el("div", { class: "comfymodal-settings-segmented", "data-testid": "settings-run-mode" });
    const cloudBtn = el("button", {
      type: "button",
      class: "comfymodal-settings-segment" + (isCloud ? " active" : ""),
      "data-testid": "settings-run-mode-cloud",
      text: "Cloud",
    });
    const localBtn = el("button", {
      type: "button",
      class: "comfymodal-settings-segment" + (!isCloud ? " active" : ""),
      "data-testid": "settings-run-mode-local",
      text: "Local",
    });
    function updateRunMode(cloud) {
      isCloud = cloud;
      cloudBtn.classList.toggle("active", cloud);
      localBtn.classList.toggle("active", !cloud);
      try { localStorage.setItem("comfymodal_enabled", String(cloud)); } catch (_) {}
      window._comfyModalEnabled = cloud;
    }
    cloudBtn.addEventListener("click", () => updateRunMode(true));
    localBtn.addEventListener("click", () => updateRunMode(false));
    seg.appendChild(cloudBtn);
    seg.appendChild(localBtn);

    section.appendChild(controlRow("Run mode", seg, "Cloud mode sends generations to Modal. Local mode runs on your machine.", "cloud local"));
    section.appendChild(infoRow("Primary navigation: Playground / History / Workflows / Settings. Backend remains available in navigation."));
    return section;
  }

  // ── 2. Generation ──
  function buildGenerationSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "generation" });
    section.appendChild(buildSectionHeader("Generation", "settings-reset-generation"));

    // Execution Engine (server-persisted; v2/v1)
    const engineSelect = el("select", { class: "comfymodal-input", "data-testid": "settings-execution-engine" });
    engineSelect.style.cssText = "width:100%;font-size:11px;padding:3px 6px;";
    const engineStatus = el("div", {
      class: "comfymodal-studio-settings-status",
      "data-testid": "settings-execution-engine-status",
    });
    const engineReadiness = el("div", {
      class: "comfymodal-studio-settings-status",
      "data-testid": "settings-execution-engine-readiness",
    });
    const engineWrap = el("div", {
      class: "comfymodal-settings-control",
      "data-search": "execution engine v2 v1 applies to future runs only",
    });
    engineWrap.appendChild(settingsRow("Execution Engine", engineSelect));
    engineWrap.appendChild(engineStatus);
    engineWrap.appendChild(engineReadiness);
    section.appendChild(engineWrap);

    // GPU (server-backed + localStorage comfymodal_gpu + window._comfyModalGpu)
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

    section.appendChild(infoRow("V1 engine remains available as a fallback for troubleshooting"));
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
    section.appendChild(infoRow("Run history is stored locally; no retention limit setting exists today."));
    return section;
  }

  // ── 5. Experiments ──
  function buildExperimentsSection() {
    const section = el("div", { class: "comfymodal-studio-settings-section", "data-section": "experiments" });
    section.appendChild(buildSectionHeader("Experiments", "settings-reset-experiments"));
    section.appendChild(infoRow("Experiment scheduling uses the fixed global backend width of 6. No per-experiment override is available."));
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
      "data-search": "runtime backend deploy state snapshots presets backends",
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

    const backendWrap = el("div", { class: "comfymodal-settings-control", "data-search": "backends" });
    backendWrap.appendChild(settingsRow("Backends", el("span", {
      class: "comfymodal-studio-settings-row-value",
      "data-testid": "settings-runtime-backends",
      text: "\u2014",
    })));
    runtimeGroup.appendChild(backendWrap);

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

    // Legacy group — all six legacy tabs embed via renderLegacyView
    function openLegacyTab(tab) {
      state.settings.activeLegacyTab = tab;
      while (container.firstChild) container.removeChild(container.firstChild);
      container.appendChild(renderLegacyView(state, context));
    }

    const legacyGroup = el("div", {
      class: "comfymodal-settings-group",
      "data-search": "legacy dashboard setup profiles results history settings",
    });
    legacyGroup.appendChild(el("h4", { class: "comfymodal-settings-group-title", text: "Legacy" }));

    const openLegacyWrap = el("div", { class: "comfymodal-settings-control", "data-search": "open legacy settings" });
    openLegacyWrap.appendChild(el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-settings-legacy-open",
      "data-testid": "settings-legacy-open",
      text: "Open Legacy Settings",
      onclick: () => openLegacyTab("settings"),
    }));
    legacyGroup.appendChild(openLegacyWrap);

    const legacyList = el("ul", { class: "comfymodal-studio-legacy-list" });
    const legacyItems = [
      { tab: "dashboard", label: "Legacy Dashboard", testid: "settings-legacy-dashboard" },
      { tab: "setup", label: "Legacy Setup", testid: "settings-legacy-setup" },
      { tab: "profiles", label: "Legacy Profiles", testid: "settings-legacy-profiles" },
      { tab: "results", label: "Legacy Results", testid: "settings-legacy-results" },
      { tab: "history", label: "Legacy History", testid: "settings-legacy-history" },
      { tab: "settings", label: "Legacy Settings", testid: "settings-legacy-settings" },
    ];
    legacyItems.forEach((item) => {
      const li = el("li", {
        class: "comfymodal-studio-legacy-item",
        "data-testid": item.testid,
        "data-search": item.label.toLowerCase(),
        text: item.label,
      });
      li.addEventListener("click", () => openLegacyTab(item.tab));
      legacyList.appendChild(li);
    });
    legacyGroup.appendChild(legacyList);
    section.appendChild(legacyGroup);

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
        text: "Reset all Studio settings to defaults. User data (workflows, history, snapshots, presets, drafts, assets) is preserved.",
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
    refreshEngineConfig(apiBase);
    refreshGpuConfig(apiBase);
    refreshDeployStatus(apiBase);
    refreshRuntimeCounts(apiBase);
    refreshOutputsPrefs(apiBase);
    refreshProfileLevel(apiBase);
  }

  // ── Execution Engine refresh (server-backed) ──
  function refreshEngineConfig(base) {
    const engineSelect = sectionsHost.querySelector('[data-testid="settings-execution-engine"]');
    if (!engineSelect) return;
    const engineStatus = sectionsHost.querySelector('[data-testid="settings-execution-engine-status"]');
    const engineReadiness = sectionsHost.querySelector('[data-testid="settings-execution-engine-readiness"]');

    function renderEngineConfig(cfg) {
      const modes = Array.isArray(cfg && cfg.available_execution_modes)
        ? cfg.available_execution_modes
        : [
            { value: "v2", label: "V2 - Recommended" },
            { value: "v1", label: "V1 - Legacy fallback" },
          ];
      while (engineSelect.firstChild) engineSelect.removeChild(engineSelect.firstChild);
      modes.forEach((mode) => {
        const option = document.createElement("option");
        option.value = mode.value;
        option.textContent = mode.label;
        engineSelect.appendChild(option);
      });
      const current = cfg && cfg.execution_mode ? cfg.execution_mode : "v2";
      engineSelect.value = current;
      window._comfyModalExecutionMode = current;
      const locked = !!(cfg && cfg.execution_mode_locked);
      engineSelect.disabled = locked;
      if (engineStatus) {
        engineStatus.textContent = locked
          ? "Managed by COMFYMODAL_RUNTIME"
          : "Current engine: " + String(current).toUpperCase() + " - Applies to future runs only";
        engineStatus.style.color = locked ? "#fbbf24" : "#888";
      }
      if (engineReadiness) {
        const readiness = cfg && cfg.execution_readiness;
        if (readiness) {
          const v1 = readiness.v1 && readiness.v1.status ? readiness.v1.status : "unknown";
          const v2 = readiness.v2 && readiness.v2.status ? readiness.v2.status : "unknown";
          engineReadiness.textContent = "V1 deployment: " + v1 + "  V2 deployment: " + v2;
          engineReadiness.style.color = v2 === "unavailable" ? "#f87171" : "#888";
        } else {
          engineReadiness.textContent = "";
        }
      }
    }

    fetch(base + "/config")
      .then((response) => response.json())
      .then(renderEngineConfig)
      .catch(() => {
        renderEngineConfig({ execution_mode: "v2", execution_mode_locked: false });
        if (engineStatus) engineStatus.textContent = "Current engine: V2 - Applies to future runs only - server status unknown";
      });

    engineSelect.addEventListener("change", async () => {
      const selected = engineSelect.value;
      engineSelect.disabled = true;
      try {
        const response = await fetch(base + "/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ execution_mode: selected }),
        });
        const data = await response.json();
        if (!response.ok || data.status === "error") throw new Error(data.message || "Could not save execution engine");
        window._comfyModalExecutionMode = selected;
        window.dispatchEvent(new CustomEvent("comfymodal:execution-mode-changed", { detail: data }));
        if (engineStatus) engineStatus.textContent = "Current engine: " + selected.toUpperCase() + " - Applies to future runs only";
      } catch (error) {
        if (engineStatus) {
          engineStatus.textContent = error.message || "Could not save execution engine";
          engineStatus.style.color = "#f87171";
        }
      } finally {
        engineSelect.disabled = false;
      }
    });

    // Keyed window listener: remove the previous handler before attaching a
    // new one so repeated renders do not accumulate listeners.
    if (_executionModeListener) {
      window.removeEventListener("comfymodal:execution-mode-changed", _executionModeListener);
    }
    _executionModeListener = (event) => {
      const detail = event && event.detail;
      if (detail && detail.execution_mode) renderEngineConfig(detail);
    };
    window.addEventListener("comfymodal:execution-mode-changed", _executionModeListener);
  }

  // ── GPU refresh (server-backed + localStorage) ──
  function refreshGpuConfig(base) {
    const gpuSelect = sectionsHost.querySelector('[data-testid="settings-gpu"]');
    if (!gpuSelect) return;

    fetch(base + "/config")
      .then((r) => r.json())
      .then((cfg) => {
        const options = Array.isArray(cfg && cfg.available_gpus) ? cfg.available_gpus : [];
        const storedGpu = localStorage.getItem("comfymodal_gpu") || "";
        const values = new Set(options.map((o) => o.value));
        const selected = storedGpu && values.has(storedGpu)
          ? storedGpu
          : (cfg.gpu || cfg.default_gpu || "rtx-pro-6000");
        while (gpuSelect.firstChild) gpuSelect.removeChild(gpuSelect.firstChild);
        if (options.length === 0) {
          gpuSelect.appendChild(el("option", { value: "rtx-pro-6000", text: "rtx-pro-6000 (default)" }));
        } else {
          options.forEach((o) => {
            gpuSelect.appendChild(el("option", { value: o.value, text: o.label || o.value }));
          });
        }
        gpuSelect.value = selected;
        window._comfyModalGpu = selected;
      })
      .catch(() => {});

    gpuSelect.addEventListener("change", async () => {
      const gpu = gpuSelect.value;
      try { localStorage.setItem("comfymodal_gpu", gpu); } catch (_) {}
      window._comfyModalGpu = gpu;
      try {
        await fetch(base + "/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gpu: gpu }),
        });
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
    const backendEl = sectionsHost.querySelector('[data-testid="settings-runtime-backends"]');
    if (!snapEl && !presetEl && !backendEl) return;

    Promise.all([
      fetch(base + "/studio/snapshots").then((r) => r.json()).catch(() => ({})),
      fetch(base + "/studio/presets").then((r) => r.json()).catch(() => ({})),
      fetch(base + "/studio/backends").then((r) => r.json()).catch(() => ({})),
    ]).then(([snapData, presetData, backendData]) => {
      if (snapEl) snapEl.textContent = String((snapData && snapData.snapshots ? snapData.snapshots.length : 0));
      if (presetEl) presetEl.textContent = String((presetData && presetData.presets ? presetData.presets.length : 0));
      if (backendEl) backendEl.textContent = String((backendData && backendData.backends ? backendData.backends.length : 0));
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
  function refreshProfileLevel(base) {
    const tracingSelect = sectionsHost.querySelector('[data-testid="settings-heavy-tracing"]');

    function updateBanner(effective) {
      const stored = localStorage.getItem("comfymodal_heavy_tracing") || "off";
      bannerEl.style.display = stored !== effective ? "flex" : "none";
    }

    if (tracingSelect) {
      const stored = localStorage.getItem("comfymodal_heavy_tracing") || "off";
      tracingSelect.value = HEAVY_TRACING_LEVELS.indexOf(stored) !== -1 ? stored : "off";
      tracingSelect.addEventListener("change", async () => {
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
        } catch (_) {
          tracingSelect.value = prev;
          try { localStorage.setItem("comfymodal_heavy_tracing", prev); } catch (e2) {}
        }
        updateBanner(effectiveTracingLevel);
      });
    }

    fetch(base + "/profile/level")
      .then((r) => r.json())
      .then((data) => {
        const effective = (data && data.effective) || "off";
        effectiveTracingLevel = effective;
        updateBanner(effective);
      })
      .catch(() => { bannerEl.style.display = "none"; });
  }

  // Initial build
  rebuildPage();
  return container;
}

// ── Legacy wrapper view ──────────────────────────────────────────────────

export function renderLegacyView(state, context) {
  const wrapper = document.createElement("div");
  wrapper.className = "comfymodal-studio-legacy";

  const backBtn = document.createElement("button");
  backBtn.className = "comfymodal-secondary-btn";
  backBtn.textContent = "\u2190 Back to Settings";
  backBtn.style.marginBottom = "16px";
  backBtn.addEventListener("click", () => {
    state.settings.activeLegacyTab = "";
    if (context && context.setPage) {
      context.setPage("settings");
    }
  });
  wrapper.appendChild(backBtn);

  const legacyBody = document.createElement("div");
  legacyBody.className = "comfymodal-studio-legacy-body";
  wrapper.appendChild(legacyBody);

  if (context && context.mountLegacyTab) {
    context.mountLegacyTab(legacyBody, state.settings.activeLegacyTab, context);
  } else {
    legacyBody.innerHTML =
      '<div class="comfymodal-studio-card"><p>Legacy wrapper not available.</p></div>';
  }

  return wrapper;
}
