// Modal Studio — Lightweight A/B Image Compare (Phase I5)
//
// Client-only, transient comparison of EXACTLY TWO existing images.
// No Comparison Profiles, no Comparison Runner, no graph-slot mutation,
// no V1 execution, no persistence, no History schema change, no backend
// writes, no new routes. The retired Comparison product stays retired.
//
// Structure:
//   1. Pure session model (Node-testable, DOM-free):
//      normalizeImageDescriptor / clampPercent / createCompareSessionModel
//   2. Transient session singleton + non-modal selection tray anchored to
//      the live History page root. Leaving the History/Experiment product
//      context (anchor detached) tears the session down. Nothing is ever
//      written anywhere.
//   3. Modal compare VIEW: two images in one fitted stage; B is clipped by
//      a single divider authority (0–100%). Keyboard-operable role="slider"
//      plus pointer drag/click on the same authority. Escape (layer 3,
//      shared registry — newest handler wins over the detail overlay's
//      older layer-3 entry) closes the view, clears the session and
//      restores focus to the invoker (stable re-resolution when the
//      invoking DOM was rebuilt).
//
// The old dead studio-ui.js viewer helpers (createZoomableImageEl /
// createImagePreviewOverlay) were evaluated as the host: they are built
// around ONE zoomable image whose pan/zoom transform would have to be kept
// pixel-aligned across two independently clipped layers, which their
// single-image architecture does not model. This module therefore reuses
// only the generic primitives (el(), registerLayerHandler) and keeps its
// own smaller aligned-stage implementation.

import { el, registerLayerHandler } from "./studio-ui.js";

const COMPARE_NARROW_QUERY = "(max-width: 640px)";
const DEFAULT_POSITION = 50;

// ── 1. Pure model ─────────────────────────────────────────────────────────

/** Last-6 identity tail for human labels ("Generation #b12cdf"). */
export function shortIdTail(id) {
  const s = id == null ? "" : String(id);
  if (!s) return "";
  const tail = s.length > 6 ? s.slice(-6) : s;
  return "#" + tail;
}

/** Clamp any numeric-ish input to an integer percent 0–100; NaN → null. */
export function clampPercent(value) {
  const n = Math.round(Number(value));
  if (isNaN(n)) return null;
  return Math.max(0, Math.min(100, n));
}

/**
 * Normalize caller-supplied presentation data into a safe image descriptor.
 * Only existing client-side presentation fields are accepted (URL, human
 * label, optional display id tail, optional alt). Mutable History records
 * or backend models are never stored. Returns null for anything unusable
 * (fail-soft, never throws).
 */
export function normalizeImageDescriptor(input) {
  if (!input || typeof input !== "object") return null;
  const url = typeof input.url === "string" ? input.url.trim() : "";
  if (!url) return null;
  let label = typeof input.label === "string" ? input.label.trim() : "";
  if (!label) label = "Image";
  if (label.length > 80) label = label.slice(0, 80);
  let meta = typeof input.meta === "string" ? input.meta.trim() : "";
  if (meta.length > 120) meta = meta.slice(0, 120);
  const kind = typeof input.kind === "string" && input.kind ? input.kind : "image";
  const alt = typeof input.alt === "string" && input.alt.trim() ? input.alt.trim() : label;
  return { url: url, label: label, kind: kind, meta: meta, alt: alt };
}

/**
 * Pure compare-session state machine.
 * Exactly two slots: A (stable until explicitly changed/reset) and B
 * (filled by the second pick; a further eligible pick REPLACES B).
 * Position is the single divider authority (integer 0–100, default 50).
 */
export function createCompareSessionModel(options) {
  const opts = options && typeof options === "object" ? options : {};
  const normalize = typeof opts.normalize === "function" ? opts.normalize : normalizeImageDescriptor;
  const onChange = typeof opts.onChange === "function" ? opts.onChange : null;

  let a = null;
  let b = null;
  let position = DEFAULT_POSITION;

  function _changed() {
    if (onChange) onChange(getState());
  }

  function getState() {
    return { a: a, b: b, position: position };
  }

  function setPosition(value) {
    const next = clampPercent(value);
    if (next == null) return false;
    position = next;
    _changed();
    return true;
  }

  return {
    getState: getState,
    setPosition: setPosition,
    /** Nudge by a signed delta, clamped to 0–100. Invalid delta → no-op. */
    nudgePosition(delta) {
      if (isNaN(Number(delta))) return false;
      return setPosition(position + Number(delta));
    },
    /**
     * Select A. An explicit new A starts a FRESH pair: any previously
     * filled B is discarded rather than silently mixed with a new base.
     */
    setA(input) {
      const desc = normalize(input);
      if (!desc) return false;
      a = desc;
      b = null;
      _changed();
      return true;
    },
    setB(input) {
      const desc = normalize(input);
      if (!desc) return false;
      b = desc;
      _changed();
      return true;
    },
    /** Explicit reset: clears both slots and restores the default position. */
    reset() {
      a = null;
      b = null;
      position = DEFAULT_POSITION;
      _changed();
    },
  };
}

// ── 2. Transient session + tray ───────────────────────────────────────────

const _session = createCompareSessionModel();

let _tray = null;
let _anchor = null;
let _observer = null;
let _originInvoker = null;

export function getCompareState() {
  return _session.getState();
}

export function isCompareActive() {
  const st = _session.getState();
  return !!(st.a || st.b);
}

function _resolveInvoker(invoker) {
  if (!invoker || typeof invoker.focus !== "function") return null;
  if (invoker.isConnected) return invoker;
  if (typeof invoker.getAttribute !== "function") return null;
  // Stable re-resolution (I4-analog): the invoking DOM may have been
  // rebuilt while the view was open. Prefer the testid+id pair; compare
  // actions carry only a unique testid, so fall back to that alone.
  const tid = invoker.getAttribute("data-testid");
  const did = invoker.getAttribute("data-id");
  try {
    if (tid && did) {
      const paired = document.querySelector('[data-testid="' + tid + '"][data-id="' + did + '"]');
      if (paired) return paired;
    }
    if (tid) return document.querySelector('[data-testid="' + tid + '"]') || null;
  } catch (err) { /* keep null */ }
  return null;
}

function _teardownSession() {
  _session.reset();
  _originInvoker = null;
  _anchor = null;
  if (_observer) {
    _observer.disconnect();
    _observer = null;
  }
  _closeView(false);
  if (_tray && _tray.parentNode) _tray.remove();
  _tray = null;
}

function _onBodyMutated() {
  const anchorGone = !_anchor || !_anchor.isConnected;
  const trayOrphaned = _tray != null && !_tray.isConnected;
  if (anchorGone || trayOrphaned) _teardownSession();
}

function _ensureTray() {
  // Prefer the History page as liveness anchor (navigating away tears the
  // session down); fall back to document.body so Playground-initiated
  // compares (e.g. the topbar Compare picker) can open anywhere.
  const anchor = document.querySelector('[data-testid="history-v2-page"]') || document.body;
  if (!anchor) {
    _teardownSession();
    return false;
  }
  _anchor = anchor;
  if (!_tray || !_tray.isConnected) {
    _tray = el("div", {
      class: "cm-compare-tray",
      "data-testid": "cm-compare-tray",
      role: "region",
      "aria-label": "Image compare selection",
    });
    document.body.appendChild(_tray);
  }
  if (!_observer) {
    try {
      _observer = new MutationObserver(_onBodyMutated);
      _observer.observe(document.body, { childList: true, subtree: true });
    } catch (err) {
      _observer = null;
    }
  }
  return true;
}

function _slotText(desc) {
  return desc ? desc.label + (desc.meta ? " \u00b7 " + desc.meta : "") : "";
}

function _renderTray() {
  if (!_tray) return;
  while (_tray.firstChild) _tray.removeChild(_tray.firstChild);
  const st = _session.getState();
  if (!st.a && !st.b) return;
  _tray.appendChild(el("span", { class: "cm-compare-tray-title", text: "Compare" }));
  _tray.appendChild(el("span", {
    class: "cm-compare-tray-slot",
    "data-testid": "cm-compare-tray-a",
    text: "A: " + (_slotText(st.a) || "not chosen"),
  }));
  _tray.appendChild(el("span", {
    class: "cm-compare-tray-slot",
    "data-testid": "cm-compare-tray-b",
    text: "B: " + (_slotText(st.b) || "not chosen"),
  }));
  const openBtn = el("button", {
    class: "comfymodal-secondary-btn cm-compare-tray-btn",
    "data-testid": "cm-compare-open",
    type: "button",
    text: "Compare images",
    disabled: !(st.a && st.b),
    onclick: function () {
      if (openBtn.disabled) return;
      openCompareView(openBtn);
    },
  });
  _tray.appendChild(openBtn);
  _tray.appendChild(el("button", {
    class: "comfymodal-secondary-btn cm-compare-tray-btn",
    "data-testid": "cm-compare-clear",
    type: "button",
    text: "Clear",
    title: "Ends the compare selection",
    onclick: function () { _teardownSession(); },
  }));
}

/** Start/restart a session with the invoking image as A (an explicit new A
 * discards any previous pairing — the model keeps pairs coherent). */
export function startCompare(payload) {
  const p = payload && typeof payload === "object" ? payload : {};
  if (!_ensureTray()) return false;
  if (!_session.setA(p.descriptor)) return false;
  if (p.invoker) _originInvoker = p.invoker;
  _renderTray();
  return true;
}

/** Fill B; when B already exists the new image truthfully replaces it. */
export function addToCompareB(payload) {
  const p = payload && typeof payload === "object" ? payload : {};
  const st = _session.getState();
  if (!st.a) return false;
  if (!_session.setB(p.descriptor)) return false;
  if (p.invoker && !_originInvoker) _originInvoker = p.invoker;
  _renderTray();
  return true;
}

/**
 * One-click pair compare (e.g. Preview vs Original): sets A+B and opens
 * the view immediately. Both descriptors must be usable; otherwise the
 * call fails soft and mutates nothing.
 */
export function openComparePair(payload) {
  const p = payload && typeof payload === "object" ? payload : {};
  if (!_ensureTray()) return false;
  if (!_session.setA(p.a)) return false;
  if (!_session.setB(p.b)) {
    _session.reset();
    _teardownSession();
    return false;
  }
  if (p.invoker) _originInvoker = p.invoker;
  _renderTray();
  openCompareView(p.invoker || null);
  return true;
}

export function clearCompareSession() {
  _teardownSession();
}

/**
 * Menu/action-row item that fills (or truthfully replaces) slot B.
 * Returns null when no session is active or the descriptor is unusable —
 * callers simply skip appending, so non-image records never expose it.
 */
export function buildAddToCompareItem(payload) {
  const p = payload && typeof payload === "object" ? payload : {};
  const st = _session.getState();
  if (!st.a) return null;
  const desc = normalizeImageDescriptor(p.descriptor);
  if (!desc) return null;
  const replaces = !!st.b;
  const btn = el("button", {
    class: p.className || "comfymodal-studio-history-v2-menu-item",
    "data-testid": p.testId || "cm-compare-add-b",
    type: "button",
    onclick: function () {
      addToCompareB({ descriptor: desc, invoker: btn });
    },
  });
  btn.appendChild(document.createTextNode("Add to compare (B)"));
  if (replaces) {
    btn.appendChild(el("span", {
      class: "cm-compare-replace-hint",
      text: "Replaces B",
    }));
  }
  return btn;
}

// ── 3. Compare view ───────────────────────────────────────────────────────

let _view = null;

function _pctFromEvent(e, stage, mode) {
  const r = stage.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return null;
  const raw = mode === "stacked"
    ? ((e.clientY - r.top) / r.height) * 100
    : ((e.clientX - r.left) / r.width) * 100;
  return clampPercent(raw);
}

/**
 * Open the modal compare view for the current session (requires both slots
 * filled). Exposed for programmatic entry and tests; the tray button is the
 * production caller. Fail-soft when the session is incomplete.
 */
export function openCompareView(opener) {
  const st = _session.getState();
  if (!st.a || !st.b || _view) return false;

  const overlay = el("div", {
    class: "cm-compare-overlay",
    "data-testid": "cm-compare-overlay",
  });
  const backdrop = el("div", { class: "cm-compare-backdrop" });
  overlay.appendChild(backdrop);

  const dialog = el("div", {
    class: "cm-compare-dialog",
    "data-testid": "cm-compare-dialog",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": "Image comparison: " + st.a.label + " versus " + st.b.label,
  });

  const header = el("div", { class: "cm-compare-header" });
  header.appendChild(el("div", {
    class: "cm-compare-title",
    "data-testid": "cm-compare-title",
    text: "Comparing " + st.a.label + " \u2194 " + st.b.label,
  }));
  const closeBtn = el("button", {
    class: "cm-compare-close",
    "data-testid": "cm-compare-close",
    type: "button",
    "aria-label": "Close comparison",
    text: "\u00d7",
    onclick: function () { _closeView(true); },
  });
  header.appendChild(closeBtn);
  dialog.appendChild(header);

  const stage = el("div", {
    class: "cm-compare-stage",
    "data-testid": "cm-compare-stage",
    "data-mode": "overlay",
  });

  const frame = el("div", { class: "cm-compare-frame" });
  const imgA = el("img", {
    class: "cm-compare-img",
    "data-testid": "cm-compare-img-a",
    src: st.a.url,
    alt: st.a.alt,
    draggable: "false",
  });
  frame.appendChild(imgA);
  const bWrap = el("div", { class: "cm-compare-bwrap", "data-testid": "cm-compare-bwrap" });
  const imgB = el("img", {
    class: "cm-compare-img",
    "data-testid": "cm-compare-img-b",
    src: st.b.url,
    alt: st.b.alt,
    draggable: "false",
  });
  bWrap.appendChild(imgB);
  frame.appendChild(bWrap);
  stage.appendChild(frame);

  function _markUnavailable(img, side) {
    img.style.display = "none";
    const note = el("div", {
      class: "cm-compare-unavailable",
      "data-testid": "cm-compare-unavailable-" + side,
      text: "Image unavailable",
    });
    frame.insertBefore(note, side === "b" ? bWrap.nextSibling : bWrap);
  }
  imgA.addEventListener("error", function () { _markUnavailable(imgA, "a"); });
  imgB.addEventListener("error", function () { _markUnavailable(imgB, "b"); });
  imgA.addEventListener("load", function () { imgA.setAttribute("data-loaded", "true"); });
  imgB.addEventListener("load", function () { imgB.setAttribute("data-loaded", "true"); });

  const labelA = el("span", {
    class: "cm-compare-label cm-compare-label-a",
    "data-testid": "cm-compare-label-a",
    text: st.a.label,
  });
  const labelB = el("span", {
    class: "cm-compare-label cm-compare-label-b",
    "data-testid": "cm-compare-label-b",
    text: st.b.label,
  });
  stage.appendChild(labelA);
  stage.appendChild(labelB);

  const divider = el("div", { class: "cm-compare-divider", "aria-hidden": "true" });
  stage.appendChild(divider);

  const slider = el("div", {
    class: "cm-compare-slider",
    "data-testid": "cm-compare-slider",
    role: "slider",
    tabindex: "0",
    "aria-label": "Comparison divider \u2014 " + st.a.label + " versus " + st.b.label,
    "aria-valuemin": "0",
    "aria-valuemax": "100",
  });
  slider.textContent = "\u21d4";
  stage.appendChild(slider);

  // ── Synchronized zoom/pan: one {scale, tx, ty} state applied IDENTICALLY
  // to both images via CSS transform, so pan/zoom stay synchronized by
  // construction. The divider authority stays untouched screen-space %{pos}.
  var zoom = { scale: 1, tx: 0, ty: 0 };
  var ZOOM_MIN = 0.1;
  var ZOOM_MAX = 8;
  var ZOOM_STEP = 1.25;
  var zoomLabel = null;
  function _clampScale(s) {
    try {
      var n = Number(s);
      if (isNaN(n)) return zoom.scale;
      return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, n));
    } catch (err) { return zoom.scale; }
  }
  function _applyZoomTransform() {
    try {
      var t = "translate(" + zoom.tx + "px, " + zoom.ty + "px) scale(" + zoom.scale + ")";
      imgA.style.transform = t;
      imgB.style.transform = t;
      imgA.style.transformOrigin = "center center";
      imgB.style.transformOrigin = "center center";
    } catch (err) { /* best-effort */ }
  }
  function _paintZoomLabel(showFit) {
    try {
      if (zoomLabel) zoomLabel.textContent = showFit ? "Fit" : Math.round(zoom.scale * 100) + "%";
    } catch (err) { /* best-effort */ }
  }
  function _zoomFit() {
    try {
      var iw = (imgA && imgA.naturalWidth) || (imgB && imgB.naturalWidth) || 0;
      var ih = (imgA && imgA.naturalHeight) || (imgB && imgB.naturalHeight) || 0;
      var fit = 1;
      try {
        var r = stage.getBoundingClientRect();
        if (iw > 0 && ih > 0 && r.width > 0 && r.height > 0) {
          fit = Math.min(r.width / iw, r.height / ih);
        }
      } catch (err2) { fit = 1; }
      zoom.scale = _clampScale(fit);
      zoom.tx = 0;
      zoom.ty = 0;
      _applyZoomTransform();
      _paintZoomLabel(true);
    } catch (err) { /* best-effort */ }
  }
  function _zoom11() {
    try {
      zoom.scale = 1;
      zoom.tx = 0;
      zoom.ty = 0;
      _applyZoomTransform();
      _paintZoomLabel(false);
    } catch (err) { /* best-effort */ }
  }
  function _zoomStep(dir) {
    try {
      if (dir < 0) zoom.scale = _clampScale(zoom.scale / ZOOM_STEP);
      else zoom.scale = _clampScale(zoom.scale * ZOOM_STEP);
      _applyZoomTransform();
      _paintZoomLabel(false);
    } catch (err) { /* best-effort */ }
  }
  var toolbar = el("div", { class: "cm-compare-zoombar", "data-testid": "cm-zoom-bar" });
  toolbar.appendChild(el("button", {
    class: "comfymodal-secondary-btn cm-zoom-btn",
    "data-testid": "cm-zoom-fit",
    type: "button",
    text: "Fit",
    title: "Fit images to stage",
    onclick: function () { _zoomFit(); },
  }));
  toolbar.appendChild(el("button", {
    class: "comfymodal-secondary-btn cm-zoom-btn",
    "data-testid": "cm-zoom-11",
    type: "button",
    text: "1:1",
    title: "Actual size",
    onclick: function () { _zoom11(); },
  }));
  toolbar.appendChild(el("button", {
    class: "comfymodal-secondary-btn cm-zoom-btn",
    "data-testid": "cm-zoom-in",
    type: "button",
    text: "+",
    title: "Zoom in",
    onclick: function () { _zoomStep(1); },
  }));
  toolbar.appendChild(el("button", {
    class: "comfymodal-secondary-btn cm-zoom-btn",
    "data-testid": "cm-zoom-out",
    type: "button",
    text: "\u2212",
    title: "Zoom out",
    onclick: function () { _zoomStep(-1); },
  }));
  zoomLabel = el("span", {
    class: "cm-zoom-label",
    "data-testid": "cm-zoom-label",
    text: "100%",
  });
  toolbar.appendChild(zoomLabel);
  dialog.appendChild(toolbar);
  dialog.appendChild(stage);
  _applyZoomTransform();

  const hint = el("div", {
    class: "cm-compare-hint",
    text: "Drag or use arrow keys \u2014 left of the divider shows " + st.a.label
      + ", right shows " + st.b.label + ". Escape closes and clears.",
  });
  dialog.appendChild(hint);
  overlay.appendChild(dialog);

  // ── Single divider authority ──
  let mode = "overlay";
  const mql = window.matchMedia(COMPARE_NARROW_QUERY);

  function _paint() {
    const pos = _session.getState().position;
    const clampedPos = pos + "%";
    if (mode === "stacked") {
      // True stacked halves: A fits the top region, B fits the bottom
      // region — the horizontal divider is their shared boundary and both
      // images preserve aspect ratio within their own half.
      imgA.style.height = clampedPos;
      bWrap.style.clipPath = "none";
      bWrap.style.top = clampedPos;
      divider.style.top = clampedPos;
      divider.style.left = "";
      slider.style.top = clampedPos;
      slider.style.left = "";
    } else {
      imgA.style.height = "";
      bWrap.style.clipPath = "inset(0 0 0 " + clampedPos + ")";
      bWrap.style.top = "";
      divider.style.left = clampedPos;
      divider.style.top = "";
      slider.style.left = clampedPos;
      slider.style.top = "";
    }
    slider.setAttribute("aria-valuenow", String(pos));
    slider.setAttribute("aria-valuetext", pos + "% " + st.b.label);
  }

  function _applyMode() {
    mode = mql.matches ? "stacked" : "overlay";
    stage.setAttribute("data-mode", mode);
    _paint();
  }

  function _onMqlChange() { _applyMode(); }
  if (typeof mql.addEventListener === "function") {
    mql.addEventListener("change", _onMqlChange);
  } else if (typeof mql.addListener === "function") {
    mql.addListener(_onMqlChange);
  }

  // Keyboard: the slider is the single keyboard surface (§8). Every
  // mutation path paints through the SAME _paint() so aria-valuenow,
  // clip geometry and the handle can never diverge from the model.
  slider.addEventListener("keydown", function (e) {
    let handled = false;
    if (e.key === "ArrowLeft") { handled = _session.nudgePosition(-5); }
    else if (e.key === "ArrowRight") { handled = _session.nudgePosition(5); }
    else if (e.key === "Home") { handled = _session.setPosition(0); }
    else if (e.key === "End") { handled = _session.setPosition(100); }
    if (handled) {
      e.preventDefault();
      _paint();
    }
  });

  // Pointer: divider-handle drags drive the single divider authority
  // (existing screen-space %{pos} behavior, transforms untouched); presses
  // starting anywhere else pan the shared zoom transform. Tiny (<3px)
  // background presses are clicks and keep the legacy divider-set behavior.
  var dragging = false;
  var dragPointerId = null;
  var dragIsPan = false;
  var panStartX = 0;
  var panStartY = 0;
  var panBaseTx = 0;
  var panBaseTy = 0;
  var panMoved = false;
  function _isDividerHandle(target) {
    try {
      if (!target) return false;
      if (target === slider || target === divider) return true;
      if (typeof target.closest === "function") {
        if (target.closest(".cm-compare-slider")) return true;
        if (target.closest(".cm-compare-divider")) return true;
      }
    } catch (err) { /* best-effort */ }
    return false;
  }
  function _onPointerDown(e) {
    try {
      if (e.button != null && e.button !== 0) return;
      if (_isDividerHandle(e.target)) {
        dragging = true;
        dragIsPan = false;
        dragPointerId = e.pointerId;
        var pct = _pctFromEvent(e, stage, mode);
        if (pct != null && _session.setPosition(pct)) _paint();
      } else {
        dragging = true;
        dragIsPan = true;
        dragPointerId = e.pointerId;
        panMoved = false;
        panStartX = e.clientX || 0;
        panStartY = e.clientY || 0;
        panBaseTx = zoom.tx;
        panBaseTy = zoom.ty;
      }
      try { stage.setPointerCapture(e.pointerId); } catch (err2) { /* drag still works */ }
      e.preventDefault();
    } catch (err) { /* best-effort */ }
  }
  function _onPointerMove(e) {
    try {
      if (!dragging || e.pointerId !== dragPointerId) return;
      if (dragIsPan) {
        var dx = (e.clientX || 0) - panStartX;
        var dy = (e.clientY || 0) - panStartY;
        if (!panMoved && Math.sqrt(dx * dx + dy * dy) < 3) return;
        panMoved = true;
        zoom.tx = panBaseTx + dx;
        zoom.ty = panBaseTy + dy;
        _applyZoomTransform();
      } else {
        var pct = _pctFromEvent(e, stage, mode);
        if (pct != null && _session.setPosition(pct)) _paint();
      }
    } catch (err) { /* best-effort */ }
  }
  function _onPointerUp(e) {
    try {
      if (!dragging || e.pointerId !== dragPointerId) return;
      if (dragIsPan && !panMoved) {
        try {
          var pct = _pctFromEvent(e, stage, mode);
          if (pct != null && _session.setPosition(pct)) _paint();
        } catch (err2) { /* best-effort */ }
      }
      dragging = false;
      dragIsPan = false;
      dragPointerId = null;
      try { stage.releasePointerCapture(e.pointerId); } catch (err3) { /* released */ }
    } catch (err) { /* best-effort */ }
  }
  try { stage.style.touchAction = "none"; } catch (err) { /* best-effort */ }
  stage.addEventListener("pointerdown", _onPointerDown);
  stage.addEventListener("pointermove", _onPointerMove);
  stage.addEventListener("pointerup", _onPointerUp);
  stage.addEventListener("pointercancel", _onPointerUp);

  // Layer 3 — registered AFTER the generation detail's layer-3 handler, so
  // the registry's newest-first ordering gives the view first refusal and
  // the next Escape reaches the underlying detail overlay.
  const unregisterLayer = registerLayerHandler(3, {
    escape: function () {
      _closeView(true);
      return true;
    },
    onKeyDown: function (e) {
      // Arrows are dispatched through the shared registry BEFORE they can
      // reach this overlay's elements (document-capture). While the slider
      // is focused, THIS handler performs the nudge on the single divider
      // authority and consumes the event so no other surface can steal or
      // double-apply it. Any other arrow focus passes through untouched.
      if (document.activeElement !== slider) return false;
      if (e.key === "ArrowLeft") {
        if (_session.nudgePosition(-5)) _paint();
        return true;
      }
      if (e.key === "ArrowRight") {
        if (_session.nudgePosition(5)) _paint();
        return true;
      }
      return false;
    },
  });

  backdrop.addEventListener("click", function () { _closeView(true); });

  document.body.appendChild(overlay);
  _applyMode();
  _paint();
  _view = {
    overlay: overlay,
    unregisterLayer: unregisterLayer,
    cleanup: function () {
      if (typeof mql.removeEventListener === "function") {
        mql.removeEventListener("change", _onMqlChange);
      } else if (typeof mql.removeListener === "function") {
        mql.removeListener(_onMqlChange);
      }
    },
    opener: opener || null,
  };

  // Focus lands on the slider (the primary control), falling back to Close.
  try { slider.focus(); } catch (err) { try { closeBtn.focus(); } catch (err2) { /* noop */ } }
  return true;
}

/**
 * Close the compare view. Closing ALWAYS ends the transient session
 * (Escape contract): A/B are cleared, the tray is removed, and focus is
 * restored to the opener — re-resolving stable testid+id identities when
 * the invoking DOM was rebuilt, then falling back to the session's origin
 * invoker (I4-style).
 */
function _closeView(restoreFocus) {
  if (!_view) return;
  const view = _view;
  _view = null;
  const opener = view.opener;
  const origin = _originInvoker;
  view.unregisterLayer();
  view.cleanup();
  if (view.overlay.parentNode) view.overlay.remove();
  // Teardown first: closing ALWAYS clears the transient session, so the
  // tray (and any opener living in it) is gone by the time focus is
  // restored — resolving beforehand would aim at soon-detached DOM.
  _teardownSession();
  if (!restoreFocus) return;
  // The opener usually lived in the now-removed tray; fall back to the
  // stable re-resolution of the session's origin invoker (I4-analog).
  const target =
    (opener && opener.isConnected && _resolveInvoker(opener)) ||
    _resolveInvoker(origin);
  if (target) {
    try { target.focus(); } catch (err) { /* detached mid-flight */ }
  }
}
