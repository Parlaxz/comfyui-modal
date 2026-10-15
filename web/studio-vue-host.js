// Modal Studio Vue preview host (Phase 1).
//
// Side-effect-free module: defining it must not touch the DOM, register
// listeners, or fetch anything — ComfyUI auto-imports every `.js` file
// under `web/` as an extension module, so top-level work here would run on
// every ComfyUI load. All work happens inside the exported functions, which
// modal-testing.js wires to the explicit `window.__comfymodalOpenVueStudio`
// preview entry. The production old Studio is untouched.
//
// Lifecycle (mirrors the settled modal-testing.js contract on purpose):
// - one Vue app mounted once, kept mounted, shown/hidden on open/close;
// - body scroll lock, background inert/aria-hidden, focus capture/restore;
// - Escape + backdrop close, no duplicate listeners;
// - explicit page opener wins over a stale URL hash for that invocation;
// - NO auto-reopen: this is a dev/test preview, never the production Studio.
// - `setGraphInteractionEnabled` is the future wizard seam: Phase 1 does
//   NOT port the workflow wizard, but the host boundary already supports
//   the graph-interaction handoff the later port needs.

const PREFIX = "[comfymodal.vue-host]";
const HOST_STYLE_ID = "comfymodal-vue-host-style";
const OVERLAY_CLASS = "comfymodal-vue-studio-overlay";

function studioAssetUrl(relative) {
  return new URL("./assets/studio/" + relative, import.meta.url).toString();
}

export function studioVueAssetUrls() {
  return {
    entry: studioAssetUrl("studio.mjs"),
    css: studioAssetUrl("studio.css"),
  };
}

let _root = null;
let _mountEl = null;
let _handle = null;
let _mountPromise = null;
let _isOpen = false;
let _triggerEl = null;
let _escListener = null;
let _backdropListener = null;
let _wizardListenersRegistered = false;
let _closeBtn = null;

// ── Future wizard seam ───────────────────────────────────────────────
// Phase 1 does not port the workflow wizard. When it arrives, the wizard
// opens over Studio while the ComfyUI graph must stay interactive; this
// capability already exists at the host boundary:
//
//   setGraphInteractionEnabled(true)  → graph interactive (wizard open):
//                                        background NOT inert, modal NOT aria-modal
//   setGraphInteractionEnabled(false) → normal Studio modal:
//                                        background inert, modal aria-modal="true"
//
// It mirrors the settled `_syncModalWizardState` invariant in
// modal-testing.js without coupling to it.
export function setGraphInteractionEnabled(enabled) {
  _inertBackground(!enabled);
  if (!_root) return;
  const modal = _root.querySelector("[data-comfymodal-studio-modal]");
  if (!modal) return;
  if (enabled) modal.removeAttribute("aria-modal");
  else modal.setAttribute("aria-modal", "true");
}

function _inertBackground(inert) {
  const targets = document.querySelectorAll(
    ".comfyui-body, #comfyui-root, .comfy-app, main, [role='main']",
  );
  const els =
    targets.length > 0
      ? targets
      : document.querySelectorAll(
          "body > :not(.comfymodal-vue-studio-host, .comfymodal-testing-host, .comfymodal-testing-fallback, script, style)",
        );
  els.forEach((node) => {
    if (node.closest && node.closest(".comfymodal-vue-studio-host")) return;
    if (inert) {
      if (!node.hasAttribute("data-vue-inert-restore")) {
        const wasInert =
          node.hasAttribute("inert") || node.getAttribute("aria-hidden") === "true";
        node.setAttribute("data-vue-inert-restore", wasInert ? "true" : "false");
      }
      node.setAttribute("inert", "");
      node.setAttribute("aria-hidden", "true");
    } else {
      node.removeAttribute("inert");
      if (node.getAttribute("data-vue-inert-restore") === "false") {
        node.removeAttribute("aria-hidden");
      }
      node.removeAttribute("data-vue-inert-restore");
    }
  });
}

function _ensureHostStyle() {
  if (document.getElementById(HOST_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = HOST_STYLE_ID;
  // Host frame only. Scoped `.cmv-` classes; no old Studio selectors, no
  // global resets. The Vue app's own design layer arrives via studio.css.
  style.textContent = [
    ".comfymodal-vue-studio-host{display:contents;}",
    "." + OVERLAY_CLASS + "{position:fixed;inset:0;z-index:60;display:flex;align-items:center;justify-content:center;background:rgba(4,8,14,.72);padding:24px;box-sizing:border-box;}",
    ".comfymodal-vue-studio-frame{position:relative;width:min(1200px,96vw);max-height:92vh;overflow:auto;border-radius:12px;box-sizing:border-box;}",
    ".comfymodal-vue-studio-close{position:absolute;top:10px;right:10px;z-index:5;width:32px;height:32px;border-radius:8px;border:1px solid #2b3542;background:#171e27;color:#e6ebf2;font-size:15px;line-height:1;cursor:pointer;}",
    ".comfymodal-vue-studio-close:hover{background:#222c38;}",
    "body.comfymodal-vue-scroll-lock{overflow:hidden;}",
  ].join("\n");
  document.head.appendChild(style);
}

function _ensureRoot() {
  if (_root && document.body.contains(_root)) return _root;
  _ensureHostStyle();
  const host = document.createElement("div");
  host.className = "comfymodal-vue-studio-host";
  const overlay = document.createElement("div");
  overlay.className = OVERLAY_CLASS;
  overlay.style.display = "none";
  const frame = document.createElement("div");
  frame.className = "comfymodal-vue-studio-frame";
  frame.setAttribute("role", "dialog");
  frame.setAttribute("aria-modal", "true");
  frame.setAttribute("aria-label", "Modal Studio Vue preview");
  frame.setAttribute("data-comfymodal-studio-modal", "");
  const closeBtn = document.createElement("button");
  closeBtn.className = "comfymodal-vue-studio-close";
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "Close Studio preview");
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", () => {
    closeStudioVue();
  });
  // Studio-contained portal target: Reka portalled UI teleports here,
  // never into document.body.
  const studio = document.createElement("div");
  studio.setAttribute("data-comfymodal-studio", "");
  const appMount = document.createElement("div");
  appMount.setAttribute("data-studio-app", "");
  const portals = document.createElement("div");
  portals.setAttribute("data-studio-portals", "");
  studio.appendChild(appMount);
  studio.appendChild(portals);
  frame.appendChild(closeBtn);
  frame.appendChild(studio);
  overlay.appendChild(frame);
  host.appendChild(overlay);
  document.body.appendChild(host);
  _root = overlay;
  _mountEl = appMount;
  _closeBtn = closeBtn;

  _backdropListener = (event) => {
    if (event.target === _root) closeStudioVue();
  };
  _root.addEventListener("click", _backdropListener);

  if (!_wizardListenersRegistered) {
    // Wizard-opening hands graph interaction BACK to ComfyUI (background
    // must accept pointer input, Studio modal must not claim aria-modal);
    // wizard-closed restores the normal inert modal. Same invariant as
    // `_syncModalWizardState` in modal-testing.js.
    document.addEventListener("comfymodal:wizard-opening", () => {
      setGraphInteractionEnabled(true);
    });
    document.addEventListener("comfymodal:wizard-closed", () => {
      if (_isOpen) setGraphInteractionEnabled(false);
    });
    _wizardListenersRegistered = true;
  }
  return _root;
}

function _ensureCss() {
  const { css } = studioVueAssetUrls();
  if (document.querySelector('link[data-comfymodal-vue-css="1"]')) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = css;
  link.setAttribute("data-comfymodal-vue-css", "1");
  document.head.appendChild(link);
}

async function _mountOnce() {
  if (_handle) return _handle;
  if (_mountPromise) return _mountPromise;
  _mountPromise = (async () => {
    _ensureCss();
    const { entry } = studioVueAssetUrls();
    const mod = await import(/* @vite-ignore */ entry);
    if (!mod || typeof mod.mountStudioPreview !== "function") {
      throw new Error(PREFIX + " studio entry has no mountStudioPreview: " + entry);
    }
    _handle = mod.mountStudioPreview(_mountEl, {});
    console.log(PREFIX, "vue app mounted once");
    return _handle;
  })();
  try {
    return await _mountPromise;
  } catch (err) {
    _mountPromise = null;
    throw err;
  }
}

function _addEscListener() {
  if (_escListener) return;
  _escListener = (event) => {
    if (event.key !== "Escape") return;
    // Layer rule: a nested open layer (Reka dialog/popover/select inside
    // the Studio portal target) owns this Escape press. Return WITHOUT
    // stopping propagation so the portalled control receives it; only
    // close Studio itself when no nested layer is open.
    if (_nestedLayerOpen()) return;
    event.stopPropagation();
    closeStudioVue();
  };
  document.addEventListener("keydown", _escListener, true);
}

// True while a portalled Studio control (Reka dialog/popover/select…,
// all of which expose data-state="open" / dialog roles) is open.
function _nestedLayerOpen() {
  if (!_root || !document.body.contains(_root)) return false;
  const portals = _root.querySelector("[data-studio-portals]");
  if (!portals) return false;
  return (
    portals.querySelector('[data-state="open"]') !== null ||
    portals.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"]') !== null
  );
}

function _removeEscListener() {
  if (!_escListener) return;
  document.removeEventListener("keydown", _escListener, true);
  _escListener = null;
}

const VUE_PAGE_KEYS = ["playground", "history", "workflows", "backend", "settings"];

export async function openStudioVue(page) {
  _ensureRoot();
  _triggerEl = document.activeElement;
  document.body.classList.add("comfymodal-vue-scroll-lock");
  _inertBackground(true);
  _root.style.display = "flex";
  _isOpen = true;
  _addEscListener();

  const handle = await _mountOnce();
  try {
    if (page && VUE_PAGE_KEYS.includes(page)) {
      await handle.router.push({ name: page });
    } else if (typeof window !== "undefined" && typeof window.location !== "undefined") {
      // No explicit page: honor a present #comfymodal= hash, else keep the
      // router where the (kept-mounted) app already is.
      const hash = window.location.hash || "";
      const match = hash.match(/^#comfymodal=(playground|history|workflows|backend|settings)(?:&focus=([^&]*))?/);
      if (match) {
        const focus = match[2] ? decodeURIComponent(match[2]) : null;
        if (focus) {
          await handle.router.push({ name: match[1], query: { focus } });
        } else {
          await handle.router.push({ name: match[1] });
        }
      }
    }
  } catch (err) {
    console.warn(PREFIX, "route apply failed:", err);
  }

  if (_closeBtn) _closeBtn.focus();
  // Dev/test inspection handle: exposes the Studio router so browser
  // validation can drive router.back()/forward()/go() directly. Not part
  // of any product contract.
  try {
    window.__comfymodalVueRouter = handle.router;
  } catch (_) {}
  return handle;
}

export function closeStudioVue() {
  if (_root && document.body.contains(_root)) {
    _root.style.display = "none";
  }
  _removeEscListener();
  _isOpen = false;
  _inertBackground(false);
  document.body.classList.remove("comfymodal-vue-scroll-lock");
  if (_triggerEl && typeof _triggerEl.focus === "function") {
    _triggerEl.focus();
    _triggerEl = null;
  }
}
