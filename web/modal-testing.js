import { app } from "../../scripts/app.js";
import { api as comfyApi } from "../../scripts/api.js";
import { ensureTestingStyles } from "./testing-styles.js";
import { fetchJson, bootstrapLoader } from "./testing-api.js";
import { createDefaultDraft, createPreviewState, normalizeDraft } from "./testing-setup-adapter.js";

// Signal to legacy sidebar modules that the unified Modal GPU tab is active.
// They should skip registering their own sidebar tabs to avoid duplicates.
window.__comfyModalUnifiedUI = true;

const MODAL_PREFIX = "/comfymodal";
const TAB_DASHBOARD = "dashboard";
const TAB_SETUP = "setup";
const TAB_PROFILES = "profiles";
const TAB_RESULTS = "results";
const TAB_HISTORY = "history";
const TAB_SETTINGS = "settings";
const PREFIX = "[comfymodal.testing]";
const HOST_CLASS = "comfymodal-testing-host";

console.log(PREFIX, "extension module imported");

const _diag = {
  moduleLoaded: true,
  extensionRegistered: false,
  setupCompleted: false,
  sidebarApiAvailable: false,
  sidebarRegistered: false,
  secondaryLauncherRegistered: false,
  fallbackLauncherVisible: false,
  modalHostMounted: false,
  modalOpen: false,
  activeTab: null,
  stylesLoaded: false,
  apiBootstrapStatus: "idle",
  eventConnectionStatus: "disconnected",
  lastFrontendError: null,
  frontendVersion: "0.1.0",
};

function updateDiag(key, value) {
  _diag[key] = value;
}

export function comfyModalTestingDiagnostics() {
  return { ..._diag };
}

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

function buildShell() {
  const overlay = el("div", { class: "comfymodal-testing-overlay" });
  const modal = el("div", { class: "comfymodal-testing-modal" });
  const header = el("div", { class: "comfymodal-testing-header" }, [
    el("h2", { text: "Modal GPU" }),
    el("button", { class: "comfymodal-testing-close", text: "✕" }),
  ]);
  const nav = el("div", { class: "comfymodal-testing-nav" }, [
    el("button", { class: "comfymodal-testing-nav-btn", "data-tab": TAB_DASHBOARD, text: "Dashboard" }),
    el("button", { class: "comfymodal-testing-nav-btn", "data-tab": TAB_SETUP, text: "Setup" }),
    el("button", { class: "comfymodal-testing-nav-btn", "data-tab": TAB_PROFILES, text: "Profiles" }),
    el("button", { class: "comfymodal-testing-nav-btn", "data-tab": TAB_RESULTS, text: "Results" }),
    el("button", { class: "comfymodal-testing-nav-btn", "data-tab": TAB_HISTORY, text: "History" }),
    el("button", { class: "comfymodal-testing-nav-btn", "data-tab": TAB_SETTINGS, text: "Settings" }),
  ]);
  const body = el("div", { class: "comfymodal-testing-body", "data-testid": "body" });
  modal.appendChild(header);
  modal.appendChild(nav);
  modal.appendChild(body);
  overlay.appendChild(modal);
  return { overlay, modal, header, nav, body };
}

let _hostEl = null;
let _isOpen = false;
let _shellCache = null;
let _currentTab = null;
let _currentController = null;

// Draft state: persists across modal close/reopen within a session.
// Keys: "setup" -> normalized draft (user intent), "results" -> experimentId, etc.
const _draftState = {};

// Runtime preview state: kept separate from the persisted draft.
// Used for preview counts, validation summaries, etc.
// This is NOT persisted and resets on each tab mount.
const _previewState = { setup: null };

// ── Browser-refresh persistence via localStorage ──────────────────────────

const DRAFT_STORAGE_KEY = "comfymodal_setup_draft";
const EXPERIMENT_ID_KEY = "comfymodal_last_experiment_id";

function _debounce(fn, ms) {
  let timer = null;
  return function (...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = null; fn.apply(this, args); }, ms);
  };
}

function _setStorageJSON(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* quota or private mode */ }
}

function _getStorageJSON(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

function _removeStorage(key) {
  try { localStorage.removeItem(key); } catch (_) { /* noop */ }
}

const _saveDraftToStorage = _debounce((draft) => {
  _setStorageJSON(DRAFT_STORAGE_KEY, draft);
}, 300);

function _loadDraftFromStorage() {
  return _getStorageJSON(DRAFT_STORAGE_KEY);
}

function _saveExperimentIdToStorage(id) {
  _setStorageJSON(EXPERIMENT_ID_KEY, id);
}

function _loadExperimentIdFromStorage() {
  return _getStorageJSON(EXPERIMENT_ID_KEY);
}

function _stopCurrentController() {
  if (_currentController && typeof _currentController.stop === "function") {
    try { _currentController.stop(); } catch (e) { }
  }
  _currentController = null;
}

function ensureHost() {
  if (_hostEl && document.body.contains(_hostEl)) return _hostEl;
  _hostEl = document.createElement("div");
  _hostEl.className = HOST_CLASS;
  _hostEl.style.display = "contents";
  document.body.appendChild(_hostEl);
  updateDiag("modalHostMounted", true);
  console.log(PREFIX, "modal host mounted");
  return _hostEl;
}

export function open_testing_modal(tabName) {
  ensureHost();
  ensureTestingStyles();
  if (_shellCache && _hostEl.contains(_shellCache.overlay)) {
    _shellCache.overlay.style.display = "flex";
    if (!_shellCache._escHandler) {
      const escHandler = (e) => {
        if (e.key === "Escape") close_testing_modal();
      };
      document.addEventListener("keydown", escHandler);
      _shellCache._escHandler = escHandler;
    }
    _isOpen = true;
    updateDiag("modalOpen", true);
    if (tabName && tabName !== _currentTab) showTab(_shellCache, tabName);
    return _shellCache;
  }
  const shell = buildShell();
  _shellCache = shell;

  // Close handler
  shell.header.querySelector(".comfymodal-testing-close").addEventListener("click", close_testing_modal);
  shell.overlay.addEventListener("click", (e) => {
    if (e.target === shell.overlay) close_testing_modal();
  });

  // Escape handler — store reference for cleanup
  const escHandler = (e) => {
    if (e.key === "Escape") close_testing_modal();
  };
  document.addEventListener("keydown", escHandler);
  shell._escHandler = escHandler;

  // Nav button click handlers
  shell.nav.querySelectorAll(".comfymodal-testing-nav-btn").forEach((b) => {
    b.addEventListener("click", () => showTab(shell, b.dataset.tab));
  });

  _hostEl.appendChild(shell.overlay);
  _isOpen = true;
  updateDiag("modalOpen", true);
  showTab(shell, tabName || TAB_DASHBOARD);
  return shell;
}

function close_testing_modal() {
  if (_shellCache && _hostEl && _hostEl.contains(_shellCache.overlay)) {
    _shellCache.overlay.style.display = "none";
    if (_shellCache._escHandler) {
      document.removeEventListener("keydown", _shellCache._escHandler);
      _shellCache._escHandler = null;
    }
  }
  _isOpen = false;
  updateDiag("modalOpen", false);
}

async function resolveModule(path) {
  try {
    return await import(path);
  } catch (e) {
    console.warn(PREFIX, "module load failed:", path, e);
    return null;
  }
}

const TAB_MODULES = {
  [TAB_DASHBOARD]: { path: "./testing-dashboard.js", fn: "dashboard_tab_render" },
  [TAB_SETUP]:    { path: "./testing-setup.js", fn: "setup_tab_render" },
  [TAB_PROFILES]: { path: "./testing-profiles.js", fn: "profiles_tab_render" },
  [TAB_RESULTS]:  { path: "./testing-results.js", fn: "results_tab_render" },
  [TAB_HISTORY]:  { path: "./testing-history.js", fn: "history_tab_render" },
  [TAB_SETTINGS]: { path: "./testing-settings.js", fn: "settings_tab_render" },
};

function mountLazyTab(container, tabName) {
  const mod = TAB_MODULES[tabName];
  if (!mod) {
    container.textContent = `Unknown tab: ${tabName}`;
    return;
  }

  const loader = bootstrapLoader(container, async () => {
    const m = await resolveModule(mod.path);
    if (m && typeof m[mod.fn] === "function") {
      while (container.firstChild) container.removeChild(container.firstChild);

      // Build options with draft state and experiment context
      const tabOptions = { apiBase: MODAL_PREFIX };

      // Inject draft state for setup
      // The normalized draft persists across close/reopen/tab switches.
      // Runtime preview state is held separately in _previewState.
      if (tabName === TAB_SETUP) {
        // Ensure stored draft is normalized; lazily create default if none
        if (!_draftState.setup) {
          _draftState.setup = _loadDraftFromStorage() || createDefaultDraft();
        }
        tabOptions.draft = normalizeDraft(_draftState.setup);
        tabOptions.onDraftChange = (draft) => {
          _draftState.setup = normalizeDraft(draft);
          _saveDraftToStorage(_draftState.setup);
          // Recompute preview state on draft change
          _previewState.setup = createPreviewState(draft);
        };
        tabOptions.onRun = (expId) => {
          if (expId) {
            _draftState.lastExperimentId = expId;
            _saveExperimentIdToStorage(expId);
            // Open Results tab after run starts
            open_testing_modal(TAB_RESULTS);
          }
        };
        // Attach preview state if available (null on first mount)
        tabOptions.previewState = _previewState.setup
          ? { ..._previewState.setup }
          : null;
      }

      // Inject experiment context for results
      if (tabName === TAB_RESULTS) {
        tabOptions.experimentId = _draftState.lastExperimentId || _loadExperimentIdFromStorage() || "";
      }

      const result = m[mod.fn](container, comfyApi, tabOptions);
      _currentController = result || null;
      _currentTab = tabName;
    } else {
      throw new Error(`Module ${mod.path} missing export ${mod.fn}`);
    }
  });
  loader.attempt();
}

function mountDashboardTab(container) { mountLazyTab(container, TAB_DASHBOARD); }
function mountSetupTab(container)    { mountLazyTab(container, TAB_SETUP); }
function mountResultsTab(container)  { mountLazyTab(container, TAB_RESULTS); }
function mountHistoryTab(container)  { mountLazyTab(container, TAB_HISTORY); }
function mountSettingsTab(container) { mountLazyTab(container, TAB_SETTINGS); }

function showTab(shell, tabName) {
  if (_currentTab && _currentTab !== tabName) {
    _stopCurrentController();
  }
  const body = shell.body;
  while (body.firstChild) body.removeChild(body.firstChild);

  // Wrap content in a page-level container for fixed-height scrolling
  const pageClass = {
    [TAB_DASHBOARD]: "testing-dashboard-page",
    [TAB_SETUP]: "testing-setup-page",
    [TAB_PROFILES]: "testing-profiles-page",
    [TAB_RESULTS]: "testing-results-page",
    [TAB_HISTORY]: "testing-history-page",
    [TAB_SETTINGS]: "",
  }[tabName] || "";

  if (pageClass) {
    const pageWrapper = el("div", { class: pageClass });
    body.appendChild(pageWrapper);
    mountLazyTab(pageWrapper, tabName);
  } else {
    mountLazyTab(body, tabName);
  }

  shell.nav.querySelectorAll(".comfymodal-testing-nav-btn").forEach((b) => {
    if (b.dataset.tab === tabName) b.classList.add("active");
    else b.classList.remove("active");
  });
  updateDiag("activeTab", tabName);
}

function buildSidebarPanel() {
  const panel = el("div", { class: "comfymodal-testing-sidebar-panel" }, [
    el("button", { text: "Open Testing Suite", onclick: () => open_testing_modal() }),
    el("div", { class: "status-row" }, [
      el("span", { text: "Deploy" }),
      el("span", { "data-testid": "sidebar-deploy", text: "—" }),
    ]),
    el("div", { class: "status-row" }, [
      el("span", { text: "Experiments" }),
      el("span", { "data-testid": "sidebar-experiments", text: "—" }),
    ]),
    el("div", { class: "status-row" }, [
      el("span", { text: "Workers" }),
      el("span", { "data-testid": "sidebar-workers", text: "—" }),
    ]),
  ]);

  (async function refreshSidebar() {
    try {
      const [deploy, exps] = await Promise.all([
        fetchJson(`${MODAL_PREFIX}/deploy/status`).catch(() => null),
        fetchJson(`${MODAL_PREFIX}/experiments`).catch(() => null),
      ]);
      const deployEl = panel.querySelector('[data-testid="sidebar-deploy"]');
      if (deployEl) deployEl.textContent = (deploy && deploy.state) || "unknown";
      const expEl = panel.querySelector('[data-testid="sidebar-experiments"]');
      const expsList = (exps && exps.experiments) || [];
      const activeExperiments = expsList.filter((e) => {
        const status = e?.snapshot?.status || e?.status;
        return status === "running" || status === "started" || status === "paused";
      });
      if (expEl) expEl.textContent = activeExperiments.length > 0 ? `${activeExperiments.length} active` : `${expsList.length} total`;
      const workerEl = panel.querySelector('[data-testid="sidebar-workers"]');
      const workerCount = activeExperiments.reduce((count, experiment) => {
        const checkpoints = experiment?.snapshot?.checkpoints || {};
        return count + Object.values(checkpoints).filter((checkpoint) => checkpoint && checkpoint.status && checkpoint.status !== "completed").length;
      }, 0);
      if (workerEl) workerEl.textContent = workerCount ? String(workerCount) : "—";
    } catch {}
  })();

  return panel;
}

let _fallbackLauncher = null;

function ensureFallbackLauncher() {
  if (_fallbackLauncher) return;
  _fallbackLauncher = el("div", { class: "comfymodal-testing-fallback" }, [
    el("button", { text: "Modal GPU", onclick: () => open_testing_modal() }),
  ]);
  document.body.appendChild(_fallbackLauncher);
  updateDiag("fallbackLauncherVisible", true);
}

function handleOpenSection(ev) {
  const sectionId = ev.detail && ev.detail.section;
  open_testing_modal(TAB_SETTINGS);
  setTimeout(() => {
    const settingsRoot = _shellCache && _shellCache.body;
    if (settingsRoot) {
      const navBtn = settingsRoot.querySelector(`[data-section="${sectionId}"]`);
      if (navBtn) navBtn.click();
    }
  }, 100);
}

window.__comfyModalTestingMarkSecondaryLauncherRegistered = function __comfyModalTestingMarkSecondaryLauncherRegistered() {
  updateDiag("secondaryLauncherRegistered", true);
};

app.registerExtension({
  name: "comfymodal.testing-suite",
  async setup() {
    console.log(PREFIX, "extension setup starting");
    updateDiag("extensionRegistered", true);

    try {
      ensureTestingStyles();
      updateDiag("stylesLoaded", true);
    } catch (e) {
      console.warn(PREFIX, "style injection issue:", e);
    }

    updateDiag("apiBootstrapStatus", "ready");
    updateDiag("eventConnectionStatus", "connected");
    console.log(PREFIX, "api bootstrap status:", _diag.apiBootstrapStatus);

    const sidebarApi = app && app.extensionManager && app.extensionManager.registerSidebarTab;
    updateDiag("sidebarApiAvailable", !!sidebarApi);

    if (sidebarApi) {
      try {
        app.extensionManager.registerSidebarTab({
          id: "comfymodal-testing-suite",
          icon: "pi pi-cloud",
          title: "Modal GPU",
          tooltip: "Modal GPU — unified testing suite & settings",
          type: "custom",
          render: async (el) => {
            el.style.height = "100%";
            el.innerHTML = "";
            el.appendChild(buildSidebarPanel());
          },
        });
        updateDiag("sidebarRegistered", true);
        console.log(PREFIX, "sidebar tab registered");
      } catch (e) {
        console.warn(PREFIX, "sidebar registration failed:", e);
        updateDiag("lastFrontendError", e.message || String(e));
        ensureFallbackLauncher();
      }
    } else {
      console.warn(PREFIX, "sidebar API not available, using fallback");
      ensureFallbackLauncher();
    }

    ensureHost();

    document.addEventListener("comfymodal.open-section", handleOpenSection);

    window.open_testing_modal = open_testing_modal;
    window.close_testing_modal = close_testing_modal;
    window.comfyModalTestingDiagnostics = comfyModalTestingDiagnostics;

    updateDiag("setupCompleted", true);
    console.log(PREFIX, "extension setup complete");
  },
});
