// Modal Studio — Settings
//
// Settings sections: Studio, Backends, Modal/Runtime, Features, Legacy.
// Legacy items are clickable and load old testing-*.js screens via
// the studio-legacy wrapper embedded inline.
// Bulky visible <p> descriptions are replaced with compact info-hint tooltips.

// ── Info Hint helper (inline, same pattern as studio-playground.js) ─────

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
  const tooltip = el("span", {
    class: "comfymodal-studio-tooltip",
    text: text,
  });
  hint.appendChild(tooltip);
  hint.addEventListener("mouseenter", () => { tooltip.style.display = "block"; });
  hint.addEventListener("mouseleave", () => { tooltip.style.display = ""; });
  hint.addEventListener("focus", () => { tooltip.style.display = "block"; });
  hint.addEventListener("blur", () => { tooltip.style.display = ""; });
  return hint;
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

  // Normal settings sections — built with DOM nodes, no bulky inline HTML blocks
  const sections = [
    {
      section: "studio",
      heading: "Studio",
      hint: "Studio preferences — theme, default page, and workspace layout options.",
    },
    {
      section: "backends",
      heading: "Backends / Presets",
      hint: "Manage backend connections, profiles, and preset configurations.",
      extra: () => {
        const link = el("a", {
          text: "Open Backend tab",
          style: "color:var(--color-accent);cursor:pointer;font-size:12px;margin-left:8px;",
          onclick: (e) => {
            e.preventDefault();
            if (context && context.setPage) context.setPage("backend");
          },
        });
        return link;
      },
    },
    {
      section: "runtime",
      heading: "Modal / Runtime",
      hint: "Runtime settings — container limits, concurrency, and timeout preferences.",
    },
    {
      section: "features",
      heading: "Features",
      hint: "Configure Studio feature availability and defaults.",
    },
  ];

  sections.forEach((sec) => {
    const sectionEl = el("div", { class: "comfymodal-studio-settings-section", "data-section": sec.section });
    const headingRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-bottom:8px;" });
    const h3 = el("h3", { text: sec.heading, style: "margin:0;font-size:12px;font-weight:600;color:#d0d0d0;" });
    headingRow.appendChild(h3);
    headingRow.appendChild(createInfoHint(sec.hint));
    if (sec.extra) {
      headingRow.appendChild(sec.extra());
    }
    sectionEl.appendChild(headingRow);
    container.appendChild(sectionEl);
  });

  // Legacy section (preserved with list + info hint)
  const legacySection = el("div", { class: "comfymodal-studio-settings-section", "data-section": "legacy" });
  const legacyHeadingRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-bottom:8px;" });
  const legacyH3 = el("h3", { text: "Legacy", style: "margin:0;font-size:12px;font-weight:600;color:#d0d0d0;" });
  legacyHeadingRow.appendChild(legacyH3);
  legacyHeadingRow.appendChild(createInfoHint("Load original testing-suite screens. Click a legacy tab to open it inside the Studio body."));
  legacySection.appendChild(legacyHeadingRow);
  const legacyList = el("ul", { class: "comfymodal-studio-legacy-list" });
  [
    { tab: "dashboard", label: "Legacy Dashboard" },
    { tab: "setup", label: "Legacy Setup" },
    { tab: "profiles", label: "Legacy Profiles" },
    { tab: "results", label: "Legacy Results" },
    { tab: "history", label: "Legacy History" },
    { tab: "settings", label: "Legacy Settings" },
  ].forEach((item) => {
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

  // Back button to return to settings sections
  const backBtn = document.createElement("button");
  backBtn.className = "comfymodal-secondary-btn";
  backBtn.textContent = "← Back to Settings";
  backBtn.style.marginBottom = "var(--space-md)";
  backBtn.addEventListener("click", () => {
    state.settings.activeLegacyTab = "";
    // Signal shell to re-render (setPage triggers full re-render)
    if (context && context.setPage) {
      context.setPage("settings");
    }
  });
  wrapper.appendChild(backBtn);

  // Container for the legacy tab content
  const legacyBody = document.createElement("div");
  legacyBody.className = "comfymodal-studio-legacy-body";
  wrapper.appendChild(legacyBody);

  // Mount the requested legacy tab via the legacy wrapper
  if (context && context.mountLegacyTab) {
    context.mountLegacyTab(legacyBody, state.settings.activeLegacyTab, context);
  } else {
    legacyBody.innerHTML =
      '<div class="comfymodal-studio-card"><p>Legacy wrapper not available.</p></div>';
  }

  return wrapper;
}
