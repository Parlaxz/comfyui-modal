// Modal Studio — Settings
//
// Settings sections with compact rows, not just headings.
// Studio: Default page Playground; Top nav with exact four pages; Theme/style Nexus-inspired
//   compact dark; Modal size Large; optional Reset UI preferences button.
// Backends / Presets: snapshot count, backend preset count, runnable count, needs binding count,
//   open Backend tab link/button.
// Modal / Runtime: deploy state or Unknown, Modal token status or Unknown, selected/default GPU
//   if available else Unknown, open Legacy Settings link/button.
// Features: Txt2Img enabled; Object Remove future image-edit tooling; Object Replace future
//   image-edit tooling; compatible backend counts per feature if available.
// Legacy: keep links/buttons for Dashboard, Setup, Profiles, Results, History, Settings.

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

function createInfoHint(text) {
  const hint = el("span", {
    class: "comfymodal-studio-info-hint",
    "data-testid": "info-hint",
    tabindex: "0",
    role: "tooltip",
    "aria-label": text,
  });
  hint.textContent = "\u24d8";
  const tooltip = el("span", { class: "comfymodal-studio-tooltip", text: text });
  hint.appendChild(tooltip);
  hint.addEventListener("mouseenter", () => { tooltip.style.display = "block"; });
  hint.addEventListener("mouseleave", () => { tooltip.style.display = ""; });
  hint.addEventListener("focus", () => { tooltip.style.display = "block"; });
  hint.addEventListener("blur", () => { tooltip.style.display = ""; });
  return hint;
}

function settingsRow(label, valueEl) {
  return el("div", { class: "comfymodal-studio-settings-row" }, [
    el("span", { class: "comfymodal-studio-settings-row-label", text: label }),
    valueEl || el("span", { class: "comfymodal-studio-settings-row-value", text: "\u2014" }),
  ]);
}

function settingsValue(value) {
  return el("span", { class: "comfymodal-studio-settings-row-value", text: String(value) });
}

export function renderSettings(state, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-settings";

  // If a legacy tab is active, render the legacy wrapper view
  if (state.settings.activeLegacyTab) {
    const legacyWrapper = renderLegacyView(state, context);
    container.appendChild(legacyWrapper);
    return container;
  }

  const apiBase = (context && context.apiBase) || "/comfymodal";

  // ── 1. Studio section ────────────────────────────────────────────────
  const studioSection = el("div", { class: "comfymodal-studio-settings-section", "data-section": "studio" });
  const studioHeadingRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-bottom:8px;" });
  studioHeadingRow.appendChild(el("h3", { text: "Studio", style: "margin:0;font-size:12px;font-weight:600;color:#d0d0d0;" }));
  studioHeadingRow.appendChild(createInfoHint("Studio preferences — default page, theme, and layout options."));
  studioSection.appendChild(studioHeadingRow);

  studioSection.appendChild(settingsRow("Default page", settingsValue("Playground")));
  studioSection.appendChild(settingsRow("Top nav pages", settingsValue("Playground | History | Backend | Settings")));
  studioSection.appendChild(settingsRow("Theme", settingsValue("Nexus-inspired compact dark")));
  studioSection.appendChild(settingsRow("Modal size", settingsValue("Large")));

  const resetBtn = el("button", {
    class: "comfymodal-secondary-btn",
    text: "Reset UI preferences",
    style: "font-size:10px;padding:3px 8px;margin-top:6px;",
    onclick: () => {
      if (confirm("Reset all UI preferences to defaults?")) {
        try {
          const keys = Object.keys(localStorage).filter(k => k.startsWith("comfymodal_"));
          keys.forEach(k => localStorage.removeItem(k));
        } catch (_) { }
      }
    },
  });
  studioSection.appendChild(el("div", { style: "margin-top:4px;" }, [resetBtn]));

  container.appendChild(studioSection);

  // ── 2. Backends / Presets section ─────────────────────────────────────
  const backendsSection = el("div", { class: "comfymodal-studio-settings-section", "data-section": "backends" });
  const backendsHeadingRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-bottom:8px;" });
  backendsHeadingRow.appendChild(el("h3", { text: "Backends / Presets", style: "margin:0;font-size:12px;font-weight:600;color:#d0d0d0;" }));
  backendsHeadingRow.appendChild(createInfoHint("Manage backend connections, profiles, and preset configurations."));
  backendsHeadingRow.appendChild(el("a", {
    text: "Open Backend tab",
    style: "color:#dc2626;cursor:pointer;font-size:12px;margin-left:8px;",
    onclick: (e) => {
      e.preventDefault();
      if (context && context.setPage) context.setPage("backend");
    },
  }));
  backendsSection.appendChild(backendsHeadingRow);

  // Async load counts
  const backendCountRow = el("div", { style: "margin-bottom:8px;" });
  backendsSection.appendChild(backendCountRow);

  Promise.all([
    fetch(`${apiBase}/studio/snapshots`).then(r => r.json()).catch(() => ({ snapshots: [] })),
    fetch(`${apiBase}/studio/presets`).then(r => r.json()).catch(() => ({ presets: [] })),
    fetch(`${apiBase}/studio/backends`).then(r => r.json()).catch(() => ({ backends: [] })),
  ]).then(([snapData, presetData, backendData]) => {
    while (backendCountRow.firstChild) backendCountRow.removeChild(backendCountRow.firstChild);
    const snapshots = snapData.snapshots || [];
    const presets = presetData.presets || [];
    const backends = backendData.backends || [];
    const runnableSnaps = snapshots.filter(s => s.status === "runnable").length;
    const needsWorkSnaps = snapshots.filter(s => s.status && s.status !== "runnable" && s.status !== "unknown").length;
    const disabledPresets = presets.filter(p => p.disabledReason).length;

    backendCountRow.appendChild(el("div", { class: "comfymodal-studio-stat-card" }, [
      settingsValue(snapshots.length),
      el("span", { text: "snapshots", style: "color:#888;" }),
    ]));
    backendCountRow.appendChild(el("div", { class: "comfymodal-studio-stat-card", style: "margin-top:4px;" }, [
      settingsValue(runnableSnaps),
      el("span", { text: "runnable", style: "color:#888;" }),
    ]));
    backendCountRow.appendChild(el("div", { class: "comfymodal-studio-stat-card", style: "margin-top:4px;" }, [
      settingsValue(presets.length),
      el("span", { text: "presets" + (disabledPresets > 0 ? ` (${disabledPresets} disabled)` : ""), style: "color:#888;" }),
    ]));
    backendCountRow.appendChild(el("div", { class: "comfymodal-studio-stat-card", style: "margin-top:4px;" }, [
      settingsValue(needsWorkSnaps),
      el("span", { text: "need binding/config", style: "color:#888;" }),
    ]));
  });

  container.appendChild(backendsSection);

  // ── 3. Modal / Runtime section ────────────────────────────────────────
  const runtimeSection = el("div", { class: "comfymodal-studio-settings-section", "data-section": "runtime" });
  const runtimeHeadingRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-bottom:8px;" });
  runtimeHeadingRow.appendChild(el("h3", { text: "Modal / Runtime", style: "margin:0;font-size:12px;font-weight:600;color:#d0d0d0;" }));
  runtimeHeadingRow.appendChild(createInfoHint("Runtime settings — container limits, concurrency, and timeout preferences."));
  runtimeHeadingRow.appendChild(el("a", {
    text: "Open Legacy Settings",
    style: "color:#dc2626;cursor:pointer;font-size:12px;margin-left:8px;",
    onclick: (e) => {
      e.preventDefault();
      state.settings.activeLegacyTab = "settings";
      while (container.firstChild) container.removeChild(container.firstChild);
      const newView = renderLegacyView(state, context);
      container.appendChild(newView);
    },
  }));
  runtimeSection.appendChild(runtimeHeadingRow);

  // Async load runtime info
  const runtimeRow = el("div", { style: "margin-bottom:4px;" });
  runtimeSection.appendChild(runtimeRow);

  fetch(`${apiBase}/deploy/status`).then(r => r.json()).then(data => {
    while (runtimeRow.firstChild) runtimeRow.removeChild(runtimeRow.firstChild);
    const deployState = (data && data.state) || "Unknown";
    const tokenSet = (data && data.token_set) || "Unknown";
    const gpu = (data && data.gpu) || "Unknown";
    runtimeRow.appendChild(settingsRow("Deploy state", settingsValue(deployState)));
    runtimeRow.appendChild(settingsRow("Modal token", settingsValue(tokenSet)));
    runtimeRow.appendChild(settingsRow("GPU", settingsValue(gpu)));
  }).catch(() => {
    runtimeRow.appendChild(settingsRow("Deploy state", settingsValue("Unknown")));
    runtimeRow.appendChild(settingsRow("Modal token", settingsValue("Unknown")));
    runtimeRow.appendChild(settingsRow("GPU", settingsValue("Unknown")));
  });

  container.appendChild(runtimeSection);

  // ── 4. Features section ──────────────────────────────────────────────
  const featuresSection = el("div", { class: "comfymodal-studio-settings-section", "data-section": "features" });
  const featuresHeadingRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-bottom:8px;" });
  featuresHeadingRow.appendChild(el("h3", { text: "Features", style: "margin:0;font-size:12px;font-weight:600;color:#d0d0d0;" }));
  featuresHeadingRow.appendChild(createInfoHint("Configure Studio feature availability and defaults."));
  featuresSection.appendChild(featuresHeadingRow);

  // Txt2Img
  featuresSection.appendChild(settingsRow("Txt2Img", el("span", { class: "comfymodal-studio-settings-row-value", style: "color:#4ade80;", text: "Enabled" })));
  // Object Remove
  featuresSection.appendChild(settingsRow("Object Remove", el("span", { class: "comfymodal-studio-settings-row-value", style: "color:#fbbf24;", text: "Future: image-edit tooling" })));
  // Object Replace
  featuresSection.appendChild(settingsRow("Object Replace", el("span", { class: "comfymodal-studio-settings-row-value", style: "color:#fbbf24;", text: "Future: image-edit tooling" })));

  // Feature counts by compatible backends (async)
  const featureCountRow = el("div", { style: "margin-top:4px;" });
  featuresSection.appendChild(featureCountRow);

  fetch(`${apiBase}/studio/backends`).then(r => r.json()).then(data => {
    const backends = data.backends || [];
    const txt2imgCount = backends.filter(b => (b.compatibleFeatures || []).includes("txt2img")).length;
    const orCount = backends.filter(b => (b.compatibleFeatures || []).includes("object_remove")).length;
    const orepCount = backends.filter(b => (b.compatibleFeatures || []).includes("object_replace")).length;
    featureCountRow.appendChild(el("p", { text: `Compatible backends: Txt2Img: ${txt2imgCount}, Object Remove: ${orCount}, Object Replace: ${orepCount}`, style: "font-size:10px;color:#555;margin:4px 0;" }));
  }).catch(() => {
    featureCountRow.appendChild(el("p", { text: "Compatible backends: unknown", style: "font-size:10px;color:#555;margin:4px 0;" }));
  });

  container.appendChild(featuresSection);

  // ── 5. Legacy section ─────────────────────────────────────────────────
  const legacySection = el("div", { class: "comfymodal-studio-settings-section", "data-section": "legacy" });
  const legacyHeadingRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-bottom:8px;" });
  legacyHeadingRow.appendChild(el("h3", { text: "Legacy", style: "margin:0;font-size:12px;font-weight:600;color:#d0d0d0;" }));
  legacyHeadingRow.appendChild(createInfoHint("Load original testing-suite screens. Click a legacy tab to open it inside the Studio body."));
  legacySection.appendChild(legacyHeadingRow);

  const legacyList = el("ul", { class: "comfymodal-studio-legacy-list" });
  const legacyItems = [
    { tab: "dashboard", label: "Legacy Dashboard" },
    { tab: "setup", label: "Legacy Setup" },
    { tab: "profiles", label: "Legacy Profiles" },
    { tab: "results", label: "Legacy Results" },
    { tab: "history", label: "Legacy History" },
    { tab: "settings", label: "Legacy Settings" },
  ];
  legacyItems.forEach((item) => {
    const li = el("li", {
      class: "comfymodal-studio-legacy-item",
      dataset: { legacyTab: item.tab },
      text: item.label,
    });
    li.addEventListener("click", () => {
      state.settings.activeLegacyTab = item.tab;
      while (container.firstChild) container.removeChild(container.firstChild);
      const newView = renderLegacyView(state, context);
      container.appendChild(newView);
    });
    legacyList.appendChild(li);
  });
  legacySection.appendChild(legacyList);
  container.appendChild(legacySection);

  return container;
}

function renderLegacyView(state, context) {
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
