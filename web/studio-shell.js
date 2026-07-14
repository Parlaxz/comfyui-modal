// Modal Studio — Shell
//
// Owns Studio app state and page switching. Renders the top nav with
// Playground, History, Backend, and Settings. Mounts the active page
// into rootEl. Receives only stable context from modal-testing.js and
// augments it with shell actions (setPage, setSettingsLegacyTab,
// mountLegacyTab).
//
// Avoids nested containers: the shell's page
// container uses a distinct class (comfymodal-studio-pagecontainer).

import { renderPlayground } from "./studio-playground.js";
import { renderHistory } from "./studio-history.js";
import { renderBackend } from "./studio-backend.js";
import { renderSettings } from "./studio-settings.js";
import { stopLegacyController } from "./studio-legacy.js";
import { el } from "./studio-ui.js";

const PAGES = {
  playground: { label: "Playground", render: renderPlayground },
  history:    { label: "History",    render: renderHistory },
  backend:    { label: "Backend",    render: renderBackend },
  settings:   { label: "Settings",   render: renderSettings },
};

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

  // Build page container — use a distinct class to avoid
  // class-name collision with page-level containers
  const pageContainer = el("div", { class: "comfymodal-studio-pagecontainer", "data-testid": "studio-page" });

  function renderActivePage(preserveScroll = true) {
    const pageScrollTop = preserveScroll ? pageContainer.scrollTop : 0;
    const controlPanelScrollTop = preserveScroll
      ? pageContainer.querySelector(".comfymodal-studio-control-panel")?.scrollTop
      : undefined;

    if (!state.playground._controlPanelScrollRestorePending) {
      const oldPanel = pageContainer.querySelector(".comfymodal-studio-control-panel");
      if (oldPanel) {
        state.playground._controlPanelScrollTop = oldPanel.scrollTop;
      }
    }

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

    pageContainer.scrollTop = pageScrollTop;
    const controlPanel = pageContainer.querySelector(".comfymodal-studio-control-panel");
    if (controlPanel && controlPanelScrollTop != null) {
      controlPanel.scrollTop = controlPanelScrollTop;
      if (controlPanel.scrollTop !== controlPanelScrollTop) {
        state.playground._controlPanelScrollRestorePending = true;
      }
    }
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
    renderActivePage(prevPage === nextPage);
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
