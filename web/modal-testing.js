import { app } from "../../scripts/app.js";
import { api as comfyApi } from "../../scripts/api.js";
import { ensureTestingStyles } from "./testing-styles.js";
import { ensureStudioStyles } from "./studio-styles.js";
import { mountStudioShell } from "./studio-shell.js";
import { parseStudioHash } from "./studio-routing.js";
import { el, registerLayerHandler } from "./studio-ui.js";

// Backward-compat flag preserved for external scripts/custom nodes that may
// still read it. Hidden legacy sidebar registrations were removed (H10);
// this module provides the single Studio sidebar entry.
window.__comfyModalUnifiedUI = true;

// ── Inert helper for background content ─────────────────────────────────

function _inertBackground(inert) {
  // Apply or remove inert/aria-hidden on ComfyUI main content behind the modal
  var targets = document.querySelectorAll(
    ".comfyui-body, #comfyui-root, .comfy-app, main, [role='main']"
  );
  if (targets.length === 0) {
    // Fallback: use :not() approach — body's children except our host
    targets = document.querySelectorAll("body > :not(.comfymodal-testing-host, .comfymodal-testing-fallback, script, style)");
  }
  targets.forEach(function (el) {
    if (inert) {
      if (!el.hasAttribute("data-inert-restore")) {
        var wasInert = el.hasAttribute("inert") || el.getAttribute("aria-hidden") === "true";
        el.setAttribute("data-inert-restore", wasInert ? "true" : "false");
      }
      el.setAttribute("inert", "");
      el.setAttribute("aria-hidden", "true");
    } else {
      el.removeAttribute("inert");
      var restore = el.getAttribute("data-inert-restore");
      if (restore === "false") {
        el.removeAttribute("aria-hidden");
      }
      el.removeAttribute("data-inert-restore");
    }
  });
}

// ── Wizard-inert invariant ──────────────────────────────────────────────
//
// Establish one rule: active .comfymodal-studio-wizard-overlay =>
//   graph background non-inert AND .comfymodal-studio-modal not
//   aria-modal (clicking the graph is intentionally permitted);
//   no wizard + open modal => background inert and aria-modal="true".

function _syncModalWizardState() {
  var wizardOv = document.querySelector(".comfymodal-studio-wizard-overlay");
  var modalRoot = document.querySelector(".comfymodal-studio-modal");
  if (wizardOv) {
    _inertBackground(false);
    if (modalRoot) modalRoot.removeAttribute("aria-modal");
  } else if (_isOpen) {
    _inertBackground(true);
    if (modalRoot) modalRoot.setAttribute("aria-modal", "true");
  }
}

const MODAL_PREFIX = "/comfymodal";
const TAB_SETUP = "setup";
const TAB_SETTINGS = "settings";
const PREFIX = "[comfymodal.testing]";
const HOST_CLASS = "comfymodal-testing-host";

// Guard for comfymodal.open-section listener (prevents duplicate registration)
let _openSectionRegistered = false;

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

function buildShell() {
  const overlay = el("div", { class: "comfymodal-testing-overlay" });
  const modal = el("div", {
    class: "comfymodal-studio-modal",
    role: "dialog",
    "aria-modal": "true",
    "aria-labelledby": "comfymodal-studio-heading",
  });
  const header = el("div", { class: "comfymodal-studio-header" }, [
    el("h1", { id: "comfymodal-studio-heading", text: "Modal GPU" }),
    el("button", {
      class: "comfymodal-testing-close",
      "aria-label": "Close modal",
      text: "✕",
    }),
  ]);
  const body = el("div", { class: "comfymodal-studio-body", "data-testid": "body" });
  modal.appendChild(header);
  modal.appendChild(body);
  overlay.appendChild(modal);
  return { overlay, modal, header, body };
}

let _hostEl = null;
let _isOpen = false;
let _shellCache = null;
let _triggerEl = null;

// ── Frozen legacy-opener redirects (H5 §22 / H10) ────────────────────────
//
// Old opener aliases land on modern owners:
//   dashboard → Backend (operational launchpad intent, re-homed by H6)
//   setup     → Playground (Experiment mode context surfaced)
//   profiles  → Playground (Comparison Profiles UI retires in Wave E)
//   results   → History (History V2 is the sole durable History)
//   history   → History
//   settings  → Settings
// Retired aliases land directly on modern pages — no dead legacy-tab state.

const ALIAS_PAGE_MAP = {
  playground: "playground",
  dashboard: "backend",
  setup: "playground",
  profiles: "playground",
  results: "history",
  history: "history",
  settings: "settings",
};

const ALIAS_DEPRECATION_MESSAGES = {
  setup: "Legacy Setup has retired. Experiments now live in Playground \u2192 Experiment mode.",
  profiles: "Comparison Profiles have retired. Preset comparisons live in Playground \u2192 Experiment mode; workflow configuration lives in Workflows.",
};

function _showAliasDeprecationNotice(alias) {
  const message = ALIAS_DEPRECATION_MESSAGES[alias];
  if (!message || !_shellCache || !_hostEl || !_hostEl.contains(_shellCache.overlay)) return;
  try { console.info(PREFIX, message); } catch (_) { }
  const body = _shellCache.body;
  if (!body) return;
  const notice = el("div", {
    "data-testid": "alias-deprecation-notice",
    text: message,
    style: "margin:0 0 12px;padding:8px 12px;border:1px solid var(--color-warning,#b45309);border-radius:6px;background:var(--color-warning-bg,#3a2e14);color:var(--color-text-primary,#e1e4ea);font-size:var(--font-size-sm,12px);",
  });
  body.insertBefore(notice, body.firstChild);
  setTimeout(() => {
    if (notice.parentNode) notice.parentNode.removeChild(notice);
  }, 6000);
}

function _applyLegacyAliasNavigation(tabName, studioApi) {
  if (!studioApi || typeof studioApi.setPage !== "function") return;
  const page = ALIAS_PAGE_MAP[tabName] || "playground";
  // Surface the existing Experiment-mode context for the retired Setup alias.
  // Uses only the pre-existing in-memory playground.experimentMode flag —
  // no new state semantics, nothing persisted.
  if (tabName === TAB_SETUP && typeof studioApi.getState === "function") {
    const shellState = studioApi.getState();
    if (shellState && shellState.playground) shellState.playground.experimentMode = true;
  }
  studioApi.setPage(page);
}

// Modal host element: the persistent mount point for the shell overlay.
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
  try {
    ensureHost();
    ensureTestingStyles();
    ensureStudioStyles();
  } catch (err) {
    console.error(PREFIX, "open_testing_modal style/host setup failed:", err);
    throw err;
  }

  // Store the current active element for focus restoration on close
  _triggerEl = document.activeElement;

  // Body scroll lock (replaces :has() pseudo-class)
  document.body.classList.add("comfymodal-body-scroll-lock");

  // Inert/aria-hidden background content so screen readers don't reach behind modal
  _inertBackground(true);

  if (_shellCache && _hostEl.contains(_shellCache.overlay)) {
    _shellCache.overlay.style.display = "flex";
    if (!_shellCache._escHandler && !_shellCache._layerBased) {
      if (!_shellCache._destroyed) {
        _shellCache._escHandler = registerLayerHandler(2, {
          escape: function () {
            if (_shellCache && _shellCache._destroyed) return false;
            close_testing_modal();
            return true;
          },
        });
        _shellCache._layerBased = true;
      }
    }
    _isOpen = true;
    updateDiag("modalOpen", true);
    // Sync wizard/modal state — if a wizard overlay already exists
    // (opened before this cached reopen), release inert + remove
    // aria-modal so the graph stays clickable.
    _syncModalWizardState();
    // Move focus into the modal
    var focusTarget = _shellCache.overlay.querySelector(".comfymodal-testing-close, .comfymodal-studio-topnav button, [data-page]");
    if (focusTarget) focusTarget.focus();
    if (tabName && _shellCache._studioApi) {
      _applyLegacyAliasNavigation(tabName, _shellCache._studioApi);
      _showAliasDeprecationNotice(tabName);
    } else if (_shellCache._studioApi && typeof _shellCache._studioApi.applyRoute === "function") {
      // I9 reopen contract: a #comfymodal= hash present in the URL (copied
      // link or set before close) is honored on the next open. Explicit
      // programmatic alias intent above takes precedence for its invocation.
      const parsed = parseStudioHash(window.location.hash);
      if (parsed.matched) {
        _shellCache._studioApi.applyRoute(
          { page: parsed.page, focus: parsed.focus },
          { rerender: true }
        );
      }
    }
    return _shellCache;
  }
  const shell = buildShell();
  _shellCache = shell;

  // Close handler
  shell.header.querySelector(".comfymodal-testing-close").addEventListener("click", close_testing_modal);
  shell.overlay.addEventListener("click", (e) => {
    if (e.target === shell.overlay) close_testing_modal();
  });

  // Layer-based Escape handler (layer 2 = dialog/shell). Tab containment is
  // provided by the inert background, not a JS focus trap.
  shell._escHandler = registerLayerHandler(2, {
    escape: function () {
      if (shell._destroyed) return false;
      close_testing_modal();
      return true;
    },
  });
  shell._layerBased = true;

  // Mount the Studio shell (replaces old 6-tab nav).
  // H18 Wave G: the legacy draft/preview/experimentId context machinery is
  // deleted — its only consumer was the retired studio-legacy.js mount
  // surface. The context now carries only what modern pages consume.
  const studioContext = {
    apiBase: MODAL_PREFIX,
    comfyApi: comfyApi,
    setPage: (page) => { if (_shellCache && _shellCache._studioApi) _shellCache._studioApi.setPage(page); },
  };
  // I9 routing precedence for THIS invocation: an explicit programmatic
  // alias opener wins over a stale URL hash — the alias target is passed as
  // the shell's initial route so the hash can never silently override it.
  // The resulting canonical route is serialized by the shell's setPage.
  // Without tabName, the shell itself honors a present #comfymodal= hash
  // (copied link / pre-reload marker) and otherwise lands on Playground.
  const mountOptions = tabName
    ? { initialRoute: { page: ALIAS_PAGE_MAP[tabName] || "playground", focus: null } }
    : {};
  const studioApi = mountStudioShell(shell.body, studioContext, mountOptions);
  shell._studioApi = studioApi;

  // Navigate to initial page if specified
  if (tabName) {
    _applyLegacyAliasNavigation(tabName, studioApi);
  }

  _hostEl.appendChild(shell.overlay);
  if (tabName) {
    _showAliasDeprecationNotice(tabName);
  }
  _isOpen = true;
  updateDiag("modalOpen", true);

  // Sync wizard/modal state — if a wizard overlay already exists
  // (e.g. opened before this first modal open), release inert + remove
  // aria-modal so the graph stays clickable.
  _syncModalWizardState();

  // Move focus into the modal
  var focusTarget = shell.overlay.querySelector(".comfymodal-testing-close, .comfymodal-studio-topnav button, [data-page]");
  if (focusTarget) focusTarget.focus();

  return shell;
}

function close_testing_modal() {
  if (_shellCache && _hostEl && _hostEl.contains(_shellCache.overlay)) {
    _shellCache.overlay.style.display = "none";
    // Clean up layer keyboard handler (idempotent)
    if (typeof _shellCache._escHandler === "function") {
      _shellCache._escHandler(); // unregister layer handler
    }
    _shellCache._escHandler = null;
    _shellCache._layerBased = false;
    _shellCache._destroyed = true;
  }
  _isOpen = false;
  updateDiag("modalOpen", false);
  // Restore inert/aria-hidden on background content to prior state
  _inertBackground(false);
  // Restore focus to the element that triggered the modal
  document.body.classList.remove("comfymodal-body-scroll-lock");
  if (_triggerEl && typeof _triggerEl.focus === "function") {
    _triggerEl.focus();
    _triggerEl = null;
  }
}

// H14 Wave E: the lazy legacy-tab machinery (TAB_MODULES/mountLazyTab) and
// the studio-legacy.js mount surface are retired. H18 Wave G deleted the
// studio-legacy.js and testing-*.js files themselves. No legacy tab is
// mountable from the Studio shell. Modern alias routing below is preserved
// unchanged (H10).

function _wrapSidebarOpener(fn, statusEl) {
  return function (ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }
    try {
      const result = fn();
      if (statusEl) {
        statusEl.textContent = "Studio open";
        statusEl.style.color = "";
      }
      return result;
    } catch (err) {
      console.error(PREFIX, "sidebar opener failed:", err);
      if (statusEl) {
        statusEl.textContent = "Open failed: " + (err && err.message ? err.message : String(err));
        statusEl.style.color = "#ef4444";
      }
      try {
        window.__comfyModalLastOpenerError = String(err && err.stack ? err.stack : err);
      } catch (_) {}
      return null;
    }
  };
}

function buildSidebarPanel() {
  const statusEl = el("div", { class: "launcher-status", "data-testid": "sidebar-launcher-status", text: "Studio shell ready" });
  const openStudioBtn = el("button", {
    text: "Open Studio",
    type: "button",
    "data-testid": "sidebar-open-studio",
    "aria-label": "Open Studio",
  });
  openStudioBtn.addEventListener("click", _wrapSidebarOpener(function () { return open_testing_modal(); }, statusEl));
  const openSettingsBtn = el("button", {
    text: "Open Settings",
    type: "button",
    "data-testid": "sidebar-open-settings",
    "aria-label": "Open Studio Settings",
  });
  openSettingsBtn.addEventListener("click", _wrapSidebarOpener(function () {
    if (statusEl) {
      statusEl.style.color = "";
      statusEl.textContent = "Opening Settings\u2026";
    }
    return open_testing_modal(TAB_SETTINGS);
  }, statusEl));
  const panel = el("div", { class: "comfymodal-testing-sidebar-panel", "data-testid": "sidebar-panel" }, [
    el("div", { class: "launcher-title", text: "Modal GPU" }),
    el("div", { class: "launcher-subtitle", text: "Playground, History, Backend, Settings" }),
    openStudioBtn,
    openSettingsBtn,
    statusEl,
  ]);
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
  // After the settings page renders, scroll to the matching section
  setTimeout(() => {
    const body = _shellCache && _shellCache.body;
    if (!body) return;
    const sectionEl = body.querySelector(`[data-section="${sectionId}"]`);
    if (sectionEl) {
      sectionEl.scrollIntoView({ behavior: "smooth", block: "start" });
      sectionEl.style.outline = "2px solid var(--color-accent)";
      setTimeout(() => { sectionEl.style.outline = ""; }, 2000);
    }
  }, 150);
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
          tooltip: "Modal GPU — Playground, History, Backend, Settings",
          type: "custom",
          render: async (containerEl) => {
            containerEl.style.height = "100%";
            while (containerEl.firstChild) containerEl.removeChild(containerEl.firstChild);
            containerEl.appendChild(buildSidebarPanel());
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

    if (!_openSectionRegistered) {
      document.addEventListener("comfymodal.open-section", handleOpenSection);
      _openSectionRegistered = true;
    }

    // Wizard inert + aria-modal handoff: centralized invariant
    // helper enforces the correct state on open/close.
    document.addEventListener("comfymodal:wizard-opening", () => {
      _syncModalWizardState();
    });
    document.addEventListener("comfymodal:wizard-closed", () => {
      _syncModalWizardState();
    });

    window.open_testing_modal = open_testing_modal;
    window.close_testing_modal = close_testing_modal;
    window.comfyModalTestingDiagnostics = comfyModalTestingDiagnostics;

    updateDiag("setupCompleted", true);
    console.log(PREFIX, "extension setup complete");
  },
});
