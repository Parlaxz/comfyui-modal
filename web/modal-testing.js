import { app } from "../../scripts/app.js";
import { api as comfyApi } from "../../scripts/api.js";
import { ensureTestingStyles } from "./testing-styles.js";
import { ensureStudioStyles } from "./studio-styles.js";
import { mountStudioShell } from "./studio-shell.js";
import { parseStudioHash } from "./studio-routing.js";
import { el, registerLayerHandler } from "./studio-ui.js";
import {
  managerRebootAndWait,
  triggerGoldenProfileDeploy,
  getGoldenProfileDeployStatus,
} from "./studio-backend-api.js";
import { loadGoldenProfileSelection } from "./studio-playground-state.js";

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

// ── Studio open persistence (refresh remembers last page) ───────────────
// sessionStorage survives a browser refresh/reload in the same tab but not a
// new tab or an explicit close: open sets the flag, close clears it. On
// extension setup a real reload with the flag set reopens the Studio modal;
// the shell's initialRoute then honors the #comfymodal=<page> hash, so the
// last page (playground/history/workflows/backend/settings) is restored. A
// persisted wizard draft forces the Workflows page so the existing
// maybeResumeSetupWizard flow can reopen the wizard at its saved step.
const STUDIO_OPEN_KEY = "comfymodal.studio.open.v1";
const WIZARD_DRAFT_STORAGE_KEY = "comfymodal.studio.wizard.draft.v1";

function _rememberStudioOpen() {
  try {
    if (typeof sessionStorage !== "undefined") sessionStorage.setItem(STUDIO_OPEN_KEY, "1");
  } catch (_err) { /* persistence is best-effort */ }
}

function _forgetStudioOpen() {
  try {
    if (typeof sessionStorage !== "undefined") sessionStorage.removeItem(STUDIO_OPEN_KEY);
  } catch (_err) { /* persistence is best-effort */ }
}

function _studioWasOpen() {
  try {
    if (typeof sessionStorage === "undefined") return false;
    return sessionStorage.getItem(STUDIO_OPEN_KEY) === "1";
  } catch (_err) {
    return false;
  }
}

function _wizardDraftPending() {
  try {
    if (typeof sessionStorage === "undefined") return false;
    const raw = sessionStorage.getItem(WIZARD_DRAFT_STORAGE_KEY);
    return typeof raw === "string" && raw !== "";
  } catch (_err) {
    return false;
  }
}

function _pageWasReloaded() {
  try {
    if (typeof performance === "undefined") return false;
    const entries =
      typeof performance.getEntriesByType === "function"
        ? performance.getEntriesByType("navigation")
        : [];
    const type = entries && entries[0] && entries[0].type;
    if (type) return type === "reload" || type === "back_forward";
    const legacy = performance.navigation;
    return !!legacy && legacy.type !== 0;
  } catch (_err) {
    return false;
  }
}

// True only on a real reload when there is something to restore: an open
// Studio (flag) or a pending wizard draft. A route hash alone never opens the
// modal, so explicitly closing Studio remains respected.
function _shouldAutoReopenStudio() {
  try {
    if (!_pageWasReloaded()) return false;
    if (_studioWasOpen()) return true;
    if (_wizardDraftPending()) return true;
    return false;
  } catch (_err) {
    return false;
  }
}

function _autoReopenStudioIfNeeded() {
  if (!_shouldAutoReopenStudio()) return;
  try {
    const shell = open_testing_modal();
    // The wizard only lives on the Workflows page. If the hash was lost
    // (ComfyUI's graph loader can overwrite it) but a draft is pending, land
    // on Workflows so maybeResumeSetupWizard can reopen the same wizard step.
    if (_wizardDraftPending() && shell && shell._studioApi) {
      const route = typeof shell._studioApi.getRoute === "function"
        ? shell._studioApi.getRoute()
        : null;
      if (!route || route.page !== "workflows") {
        if (typeof shell._studioApi.applyRoute === "function") {
          shell._studioApi.applyRoute({ page: "workflows", focus: null }, { rerender: true });
        } else if (typeof shell._studioApi.setPage === "function") {
          shell._studioApi.setPage("workflows");
        }
      }
    }
  } catch (_err) {
    console.warn(PREFIX, "studio auto-reopen failed:", _err);
  }
}

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

// Topnav restart: same explicit-reboot contract as the wizard dependencies
// section (rebootManagerAndReport → managerRebootAndWait). Fires only on
// click; the reboot POST's connection drop is expected and success is
// decided by the bounded reconnect probes, never by the POST response.
let _topnavBusy = false;

function setTopnavBusy(btn, busy) {
  _topnavBusy = busy;
  if (!btn) return;
  btn.disabled = busy;
  if (busy) btn.setAttribute("aria-busy", "true");
  else btn.removeAttribute("aria-busy");
}

async function runTopnavRestartStep(btn) {
  let res = null;
  try {
    res = await managerRebootAndWait({
      onPhase: (phase) => {
        if (!btn) return;
        btn.title = phase === "manager"
          ? "ComfyUI reconnected — waiting for ComfyUI-Manager…"
          : "Restarting ComfyUI — waiting for it to reconnect…";
      },
    });
  } catch (e) {
    res = null;
  }
  return res;
}

async function handleTopnavRestart(btn) {
  if (!btn || btn.disabled || _topnavBusy) return;
  const originalTitle = btn.title;
  setTopnavBusy(btn, true);
  btn.title = "Restarting ComfyUI — waiting for it to reconnect…";
  const res = await runTopnavRestartStep(btn);
  setTopnavBusy(btn, false);
  btn.title = (res && res.message) || originalTitle;
}

// Topnav redeploy: same POST /studio/golden/deploy contract as the Settings
// Golden-profile Deploy control, but page-agnostic (no Settings host/owner).
// Uses the persisted profile selection; bounded poll mirrors Settings.
async function runTopnavRedeployStep(btn) {
  const profile = loadGoldenProfileSelection();
  if (!profile) {
    if (btn) btn.title = "Select a Golden profile in Settings first";
    return { ok: false, message: "Select a Golden profile in Settings first" };
  }
  if (btn) btn.title = "Deploying " + profile + "…";
  let started = null;
  try {
    started = await triggerGoldenProfileDeploy(MODAL_PREFIX, profile);
  } catch (e) {
    started = null;
  }
  if (!started || started.status === "error") {
    const message = "Deploy request failed" + (started && started.message ? ": " + started.message : ".");
    if (btn) btn.title = message;
    return { ok: false, message };
  }
  for (let attempt = 0; attempt < 900; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    let payload = null;
    try {
      payload = await getGoldenProfileDeployStatus(MODAL_PREFIX, profile);
    } catch (e) {
      payload = null;
    }
    if (payload && payload.state === "done") {
      if (btn) btn.title = "Deploy finished.";
      return { ok: true, message: "Deploy finished." };
    }
    if (payload && payload.state === "failed") {
      const tail = String(payload.output || payload.message || "").trim().split("\n").pop();
      const message = "Deploy failed: " + (tail || "see v2ctl output");
      if (btn) btn.title = message;
      return { ok: false, message };
    }
  }
  if (btn) btn.title = "Deploy still running. Reopen Settings to check its status.";
  return { ok: false, message: "Deploy still running. Reopen Settings to check its status." };
}

async function handleTopnavRedeploy(btn) {
  if (!btn || btn.disabled || _topnavBusy) return;
  const originalTitle = btn.title;
  setTopnavBusy(btn, true);
  const res = await runTopnavRedeployStep(btn);
  setTopnavBusy(btn, false);
  if (res && res.ok) {
    btn.title = res.message || originalTitle;
  }
  // On failure runTopnavRedeployStep already set a descriptive title.
}

function handleTopnavHardReload() {
  location.reload();
}

// "All of the above": strictly sequential — redeploy completes, then
// ComfyUI restart completes, and only then the page reloads.
async function handleTopnavAll(btn) {
  if (!btn || btn.disabled || _topnavBusy) return;
  setTopnavBusy(btn, true);
  try {
    await runTopnavRedeployStep(btn);
    btn.title = "Restarting ComfyUI — waiting for it to reconnect…";
    await runTopnavRestartStep(btn);
  } finally {
    btn.title = "Reloading…";
    location.reload();
  }
}

function closeRestartMenu(shell) {
  if (!shell || !shell.restartMenu || !shell.restartBtn) return;
  shell.restartMenu.style.display = "none";
  shell.restartBtn.setAttribute("aria-expanded", "false");
  if (shell.nav) shell.nav.style.overflow = "";
}

function toggleRestartMenu(shell) {
  if (!shell || !shell.restartMenu || !shell.restartBtn) return;
  const open = shell.restartMenu.style.display !== "none";
  if (open) {
    closeRestartMenu(shell);
  } else {
    shell.restartMenu.style.display = "block";
    shell.restartBtn.setAttribute("aria-expanded", "true");
    // The topnav scrolls horizontally (overflow-x:auto), which would clip
    // the dropdown. While the menu is open, lift clipping; restored on close.
    if (shell.nav) shell.nav.style.overflow = "visible";
  }
}

function buildShell() {
  const overlay = el("div", { class: "comfymodal-testing-overlay" });
  const modal = el("div", {
    class: "comfymodal-studio-modal",
    role: "dialog",
    "aria-modal": "true",
    "aria-labelledby": "comfymodal-studio-heading",
  });
  const heading = el("h1", {
    id: "comfymodal-studio-heading",
    text: "Modal GPU",
    class: "comfymodal-studio-topnav-heading",
  });
  const restartBtn = el("button", {
    class: "comfymodal-studio-restart",
    type: "button",
    "data-testid": "topnav-restart-comfy",
    "aria-label": "Restart options",
    title: "Restart options",
    text: "↻",
    "aria-haspopup": "menu",
    "aria-expanded": "false",
  });
  const restartMenu = el("div", {
    class: "comfymodal-studio-restart-menu",
    "data-testid": "topnav-restart-menu",
    role: "menu",
    style: "display:none;",
  }, [
    el("button", {
      type: "button",
      class: "comfymodal-studio-restart-menu-item",
      "data-testid": "topnav-restart-comfyui",
      role: "menuitem",
      text: "Restart ComfyUI",
      onclick: (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeRestartMenu(_shellCache);
        handleTopnavRestart(_shellCache ? _shellCache.restartBtn : restartBtn);
      },
      onkeydown: (e) => e.stopPropagation(),
    }),
    el("button", {
      type: "button",
      class: "comfymodal-studio-restart-menu-item",
      "data-testid": "topnav-redeploy-golden",
      role: "menuitem",
      text: "Redeploy",
      onclick: (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeRestartMenu(_shellCache);
        handleTopnavRedeploy(_shellCache ? _shellCache.restartBtn : restartBtn);
      },
      onkeydown: (e) => e.stopPropagation(),
    }),
    el("button", {
      type: "button",
      class: "comfymodal-studio-restart-menu-item",
      "data-testid": "topnav-hard-reload",
      role: "menuitem",
      text: "Hard reload page",
      onclick: (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeRestartMenu(_shellCache);
        handleTopnavHardReload();
      },
      onkeydown: (e) => e.stopPropagation(),
    }),
    el("button", {
      type: "button",
      class: "comfymodal-studio-restart-menu-item",
      "data-testid": "topnav-restart-all",
      role: "menuitem",
      text: "All of the above",
      onclick: (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeRestartMenu(_shellCache);
        handleTopnavAll(_shellCache ? _shellCache.restartBtn : restartBtn);
      },
      onkeydown: (e) => e.stopPropagation(),
    }),
  ]);
  restartBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleRestartMenu(_shellCache);
  });
  const restartWrap = el("div", { class: "comfymodal-studio-restart-wrap" }, [restartBtn, restartMenu]);
  const topnavActions = el("div", { class: "comfymodal-studio-topnav-actions" }, [
    restartWrap,
    el("button", {
      class: "comfymodal-studio-help",
      "aria-label": "Open documentation",
      title: "Open documentation",
      text: "?",
    }),
    el("button", {
      class: "comfymodal-testing-close",
      "aria-label": "Close modal",
      text: "✕",
    }),
  ]);
  const body = el("div", { class: "comfymodal-studio-body", "data-testid": "body" });
  modal.appendChild(body);
  overlay.appendChild(modal);
  const shell = { overlay, modal, heading, topnavActions, body, restartBtn, restartMenu, restartWrap };
  document.addEventListener("click", (e) => {
    if (!_shellCache || _shellCache !== shell) return;
    if (shell.restartMenu.style.display === "none") return;
    if (shell.restartWrap.contains(e.target)) return;
    closeRestartMenu(shell);
  });
  document.addEventListener("keydown", (e) => {
    if (!_shellCache || _shellCache !== shell) return;
    if (e.key !== "Escape") return;
    if (shell.restartMenu.style.display === "none") return;
    closeRestartMenu(shell);
    e.stopPropagation();
  });
  return shell;
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

  _rememberStudioOpen();

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
            if (_shellCache && _shellCache.restartMenu
              && _shellCache.restartMenu.style.display !== "none") {
              closeRestartMenu(_shellCache);
              return true;
            }
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
  shell.topnavActions.querySelector(".comfymodal-testing-close").addEventListener("click", close_testing_modal);
  shell.topnavActions.querySelector(".comfymodal-studio-help").addEventListener("click", () => {
    window.open("/extensions/comfyui-modal/docs.html?v=" + Date.now(), "_blank", "noopener,noreferrer");
  });
  shell.overlay.addEventListener("click", (e) => {
    if (e.target === shell.overlay) close_testing_modal();
  });

  // Layer-based Escape handler (layer 2 = dialog/shell). Tab containment is
  // provided by the inert background, not a JS focus trap.
  shell._escHandler = registerLayerHandler(2, {
    escape: function () {
      if (shell._destroyed) return false;
      if (shell.restartMenu && shell.restartMenu.style.display !== "none") {
        closeRestartMenu(shell);
        return true;
      }
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
  studioApi.nav.insertBefore(shell.heading, studioApi.nav.firstChild);
  studioApi.nav.appendChild(shell.topnavActions);
  shell.nav = studioApi.nav;

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
  _forgetStudioOpen();
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
  if (_shellCache && _shellCache._studioApi && typeof _shellCache._studioApi.applyRoute === "function") {
    _shellCache._studioApi.applyRoute({ page: "settings", focus: sectionId }, { rerender: true });
  }
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

    _autoReopenStudioIfNeeded();
  },
});
