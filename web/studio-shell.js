// Modal Studio — Shell
//
// Owns Studio app state and page switching. Renders the top nav with
// Playground, History, and Settings. Mounts the active page into rootEl.
// Receives only stable context from modal-testing.js and augments it
// with shell actions (setPage, setSettingsLegacyTab, mountLegacyTab).

import { renderPlayground } from "./studio-playground.js";
import { renderHistory } from "./studio-history.js";
import { renderSettings } from "./studio-settings.js";
import { stopLegacyController } from "./studio-legacy.js";

const PAGES = {
  playground: { label: "Playground", render: renderPlayground },
  history:    { label: "History",    render: renderHistory },
  settings:   { label: "Settings",   render: renderSettings },
};

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

export function mountStudioShell(rootEl, context = {}) {
  const state = {
    activePage: "playground",
    playground: {
      featureId: "txt2img",
      experimentMode: false,
      selectedBackendId: "",
      compareBackendIds: [],
      controls: {},
      experimentAxes: {},
    },
    history: {
      selectedRunId: "",
      filters: { query: "", kind: "all", status: "all" },
    },
    settings: {
      activeSection: "studio",
      activeLegacyTab: "",
    },
  };

  // Build top nav
  const nav = el("div", { class: "comfymodal-studio-topnav" });

  // Build page container
  const pageContainer = el("div", { class: "comfymodal-studio-body", "data-testid": "studio-page" });

  function renderActivePage() {
    // Clear page container
    while (pageContainer.firstChild) pageContainer.removeChild(pageContainer.firstChild);

    const pageDef = PAGES[state.activePage];
    if (!pageDef) {
      pageContainer.textContent = `Unknown page: ${state.activePage}`;
      return;
    }

    // Augment context with shell actions so pages can trigger navigation,
    // legacy mounting, and state changes
    const pageContext = {
      ...context,
      setPage,
      setSettingsLegacyTab(tab) {
        state.settings.activeLegacyTab = tab;
        renderActivePage();
      },
      mountLegacyTab: context.mountLegacyTab,
    };

    const content = pageDef.render(state, pageContext);
    if (content) pageContainer.appendChild(content);
  }

  function updateNavActive() {
    nav.querySelectorAll("button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.page === state.activePage);
    });
  }

  // Create nav buttons
  Object.entries(PAGES).forEach(([pageId, pageDef]) => {
    const btn = el("button", {
      "data-page": pageId,
      text: pageDef.label,
      onclick: () => {
        setPage(pageId);
      },
    });
    nav.appendChild(btn);
  });

  function setPage(nextPage) {
    const prevPage = state.activePage;
    state.activePage = nextPage;
    // Stop legacy controller when navigating away from settings with active
    // legacy tab, or when closing the modal
    if (prevPage === "settings" && state.settings.activeLegacyTab) {
      stopLegacyController();
    }
    // Clear legacy tab when navigating away from settings
    if (nextPage !== "settings") {
      state.settings.activeLegacyTab = "";
    }
    updateNavActive();
    renderActivePage();
  }

  // Assemble shell
  rootEl.appendChild(nav);
  rootEl.appendChild(pageContainer);

  // Initial render
  updateNavActive();
  renderActivePage();

  const shellApi = {
    destroy() {
      while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);
    },
    setPage,
    getState() {
      return state;
    },
  };

  return shellApi;
}
