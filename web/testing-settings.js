// web/testing-settings.js
//
// Settings tab inside the Modal GPU modal.
//
// Strategy: embed the existing legacy Modal settings panel directly into
// the Settings tab body using mountSettingsPanel (exposed by modal-settings.js).
// Section navigation activates sections in the embedded panel via scroll/click.
// A fallback "Launch standalone" button is provided if the mount helper is
// not available (edge case / old version).

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k === "value") e.value = props[k];
    else if (k === "html") e.innerHTML = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
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

const SECTIONS = [
  { id: "credentials", label: "Connection & credentials" },
  { id: "deployment", label: "Deployment & runtime" },
  { id: "gpu", label: "GPU" },
  { id: "workspace", label: "Workspace" },
  { id: "models", label: "Models" },
  { id: "sync", label: "Custom nodes & sync" },
  { id: "output", label: "Output defaults" },
  { id: "tokens", label: "Tokens" },
  { id: "logs", label: "Logs & diagnostics" },
];

export function settings_tab_render(rootEl, api, options = {}) {
  if (!rootEl) throw new Error("settings_tab_render: rootEl is required");
  const apiBase = options.apiBase || "/comfymodal";

  while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);

  // Use the shared wrapper class for consistent layout
  const shell = el("div", { class: "testing-settings-root testing-settings-page comfymodal-settings-wrapper comfymodal-settings-responsive" });

  // Section navigation sidebar
  const nav = el("nav", { class: "testing-settings-nav" });

  // Body: will hold the embedded panel
  const body = el("div", { class: "testing-settings-body", "data-testid": "body" });

  // Try to embed the real legacy settings panel
  let panelMounted = false;

  function tryMountPanel() {
    if (typeof window.mountSettingsPanel === "function") {
      try {
        window.mountSettingsPanel(body);
        panelMounted = true;
        return true;
      } catch (e) {
        console.warn("[testing-settings] mountSettingsPanel failed:", e);
      }
    }
    return false;
  }

  // Fallback nav+launcher if the real panel couldn't be mounted
  function buildFallbackUI() {
    panelMounted = false;
    while (body.firstChild) body.removeChild(body.firstChild);

    body.appendChild(el("div", {
      class: "testing-settings-intro",
      text: "Use the section buttons below or launch the standalone settings panel.",
    }));

    const launchBtn = el("button", {
      class: "testing-settings-btn comfymodal-primary-btn",
      text: "Launch Standalone Settings",
    });
    launchBtn.addEventListener("click", () => {
      if (typeof window.open_comfymodal_settings === "function") {
        window.open_comfymodal_settings();
      }
    });
    body.appendChild(launchBtn);

    for (const s of SECTIONS) {
      const b = el("button", {
        class: "testing-settings-btn testing-settings-section-launch comfymodal-secondary-btn",
        "data-section": s.id,
        text: s.label,
      });
      b.addEventListener("click", () => {
        nav.querySelectorAll(".testing-settings-nav-btn").forEach((x) => x.classList.remove("active", "comfymodal-nav-btn-active"));
        b.classList.add("active", "comfymodal-nav-btn-active");
        // Dispatch to legacy panel
        document.dispatchEvent(new CustomEvent("comfymodal.open-section", {
          detail: { section: s.id },
        }));
        if (typeof window.open_comfymodal_settings === "function") {
          window.open_comfymodal_settings();
        }
      });
      body.appendChild(b);
    }
  }

  // Set initial active nav button (first section)
  const firstNavBtn = nav.querySelector(".testing-settings-nav-btn");
  if (firstNavBtn) firstNavBtn.classList.add("active", "comfymodal-nav-btn-active");

  for (const s of SECTIONS) {
    const navBtn = el("button", {
      class: "testing-settings-nav-btn",
      "data-section": s.id,
      text: s.label,
    });
    navBtn.addEventListener("click", () => {
      nav.querySelectorAll(".testing-settings-nav-btn").forEach((x) => x.classList.remove("active", "comfymodal-nav-btn-active"));
      navBtn.classList.add("active", "comfymodal-nav-btn-active");
      if (panelMounted) {
        // Scroll to the matching section in the embedded panel
        const sectionId = s.id;
        const targets = body.querySelectorAll(
          `[data-settings-section="${sectionId}"], [data-section="${sectionId}"]`
        );
        if (targets.length > 0) {
          targets[0].scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
        // Fallback: search headings for matching text
        const headings = body.querySelectorAll("h3, h4, .comfymodal-settings-section-title");
        for (const h of headings) {
          const text = (h.textContent || "").toLowerCase();
          if (text.includes(sectionId) || text.includes(s.label.toLowerCase())) {
            h.scrollIntoView({ behavior: "smooth", block: "start" });
            return;
          }
        }
        // Last resort: dispatch custom event for legacy panel to handle
        document.dispatchEvent(new CustomEvent("comfymodal.open-section", {
          detail: { section: sectionId },
        }));
      } else {
        const btn = body.querySelector(`[data-section="${s.id}"]`);
        if (btn) btn.click();
      }
    });
    nav.appendChild(navBtn);
  }

  // Try to embed the real panel first
  tryMountPanel();
  if (!panelMounted) {
    buildFallbackUI();
  } else {
    // Successfully embedded — add a "show standalone" link at the top of nav
    const standaloneLink = el("button", {
      class: "testing-settings-nav-link",
      text: "Open standalone panel",
      style: "background:none;border:none;color:var(--color-accent,#5a7fdb);cursor:pointer;font-size:var(--font-size-xs,11px);padding:4px 8px;",
    });
    standaloneLink.addEventListener("click", () => {
      if (typeof window.open_comfymodal_settings === "function") {
        window.open_comfymodal_settings();
      }
    });
    nav.appendChild(standaloneLink);
  }

  shell.appendChild(nav);
  shell.appendChild(body);
  rootEl.appendChild(shell);

  return {
    rootEl: shell,
    body,
    select: (sectionId) => {
      if (panelMounted) {
        const navBtn = nav.querySelector(`[data-section="${sectionId}"]`);
        if (navBtn) navBtn.click();
      } else {
        const btn = body.querySelector(`[data-section="${sectionId}"]`);
        if (btn) btn.click();
      }
    },
  };
}
