// Modal Studio — Shared UI Helpers
//
// Element builder, status badges, keyboard registry, zoomable image preview,
// image preview overlay, download button, and legacy empty state renderer
// shared across Backend page modules.

// ── Layer-aware Keyboard Registry ─────────────────────────────────────────
//
// Shared document-level keyboard listener with deterministic priority layers.
// Layers (highest to lowest):
//   5 — Native fullscreen (Escape exits fullscreen first)
//   4 — Enlarged zoom (Escape reduces zoom)
//   3 — Preview overlay (Escape closes preview)
//   2 — Nested dialog / shell (Escape closes dialog)
//   1 — Zoom controls (NumpadAdd / NumpadSubtract on the highest active preview)
//
// Register a handler with a layer number. Higher-numbered layers get first
// refusal via e.stopPropagation(). Escape is consumed by the highest layer
// that wants it. Layers can also handle NumpadAdd/NumpadSubtract for zoom.
//
// Usage:
//   const unreg = registerLayerHandler(3, {
//     escape: () => { closePreview(); return true; },
//     numpadAdd: () => { zoomIn(); return true; },
//     numpadSubtract: () => { zoomOut(); return true; },
//   });
//   // Later: unreg();
//
// Multiple registrations at the same layer are allowed; they are tried in
// registration order. The first handler that returns true consumes the event.

let _layerHandlers = []; // Array of { layer, id, handlers: { escape?, numpadAdd?, numpadSubtract?, onKeyDown? } }
let _layerListenerAttached = false;
let _layerIdCounter = 0;

// Track fullscreen exit so the next Escape after exiting fullscreen
// routes through normal layers instead of being absorbed by a stale
// fullscreenElement check during the exit transition.
let _fullscreenExitPending = false;

function _isEditableElement(el) {
  return el && (
    el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" ||
    el.isContentEditable
  );
}

function _dispatchLayerEvent(key, event) {
  // Sort by layer descending, then newest-first at equal priority
  // so the most recently registered handler at a given layer wins.
  var sorted = _layerHandlers.slice().sort(function (a, b) {
    if (b.layer !== a.layer) return b.layer - a.layer;
    return b._order - a._order;
  });
  for (var i = 0; i < sorted.length; i++) {
    var entry = sorted[i];
    var fn = entry.handlers[key];
    if (typeof fn === "function") {
      try {
        var consumed = fn(event);
        if (consumed === true) {
          event.preventDefault();
          event.stopPropagation();
          return true;
        }
      } catch (e) {
        // Handler error — continue to next
      }
    }
  }
  return false;
}

function _onLayerKeydown(event) {
  // Never consume keyboard events when an editable element is focused.
  // This allows normal typing in inputs, textareas, selects, etc.
  if (_isEditableElement(document.activeElement)) return;

  var key = event.key;

  // Escape chain: native fullscreen → zoom → preview → dialog → default
  if (key === "Escape") {
    // Layer 5: Native fullscreen — let the browser handle it first.
    // Use _fullscreenExitPending to distinguish the first Escape while
    // fullscreen (which should exit fullscreen) from a subsequent Escape
    // after fullscreen has already exited.
    if (document.fullscreenElement && !_fullscreenExitPending) {
      // Set flag so the next Escape (after fullscreenchange) will be
      // dispatched through normal layers instead of being skipped.
      _fullscreenExitPending = true;
      // Don't consume — let browser's native handler exit fullscreen.
      // The fullscreenchange event will clear _fullscreenExitPending.
      return;
    }
    _fullscreenExitPending = false;
    _dispatchLayerEvent("escape", event);
    return;
  }

  // NumpadAdd / NumpadSubtract: only exact event.code === "NumpadAdd" / "NumpadSubtract".
  // Do NOT consume ordinary +/-/= keys to avoid interfering with text input
  // (the editable-element check above already guards this, but the narrower
  // code check prevents false positives from keyboard layouts where +/- are
  // on shifted keys).
  if (event.code === "NumpadAdd") {
    _dispatchLayerEvent("numpadAdd", event);
    return;
  }

  if (event.code === "NumpadSubtract") {
    _dispatchLayerEvent("numpadSubtract", event);
    return;
  }

  // Arrow keys: dispatched via onKeyDown callback on each layer handler
  // (newest layer first, then registration order).  Used by preview overlays
  // and experiment grid navigation.
  if (key === "ArrowUp" || key === "ArrowDown" || key === "ArrowLeft" || key === "ArrowRight") {
    var sorted = _layerHandlers.slice().sort(function (a, b) {
      if (b.layer !== a.layer) return b.layer - a.layer;
      return b._order - a._order;
    });
    for (var i = 0; i < sorted.length; i++) {
      var entry = sorted[i];
      var fn = entry.handlers.onKeyDown;
      if (typeof fn === "function") {
        try {
          var consumed = fn(event);
          if (consumed === true) {
            event.preventDefault();
            event.stopPropagation();
            return true;
          }
        } catch (e) {
          // Handler error — continue to next
        }
      }
    }
  }
}

function _ensureLayerListener() {
  if (_layerListenerAttached) return;
  document.addEventListener("keydown", _onLayerKeydown, true); // capture phase
  document.addEventListener("fullscreenchange", _onFullscreenChangeGlobal);
  _layerListenerAttached = true;
}

function _removeLayerListenerIfEmpty() {
  if (_layerHandlers.length === 0 && _layerListenerAttached) {
    document.removeEventListener("keydown", _onLayerKeydown, true);
    document.removeEventListener("fullscreenchange", _onFullscreenChangeGlobal);
    _layerListenerAttached = false;
    _fullscreenExitPending = false;
  }
}

function _onFullscreenChangeGlobal() {
  // Clear the pending flag when fullscreen exits so the next Escape
  // keydown goes through normal layer dispatch.
  if (!document.fullscreenElement) {
    _fullscreenExitPending = false;
  }
}

/**
 * Register a keyboard handler at a given layer.
 * @param {number} layer - Priority layer (5=fullscreen, 4=zoom, 3=preview, 2=dialog, 1=base)
 * @param {object} handlers - { escape?, numpadAdd?, numpadSubtract?, onKeyDown? }
 *        Each handler receives the KeyboardEvent and should return true to consume.
 *        onKeyDown receives ALL keydown events (after Escape/numpad checks) and is
 *        used for arrow key navigation in preview overlays and experiment grids.
 * @returns {function} Unregister function
 */
export function registerLayerHandler(layer, handlers) {
  _ensureLayerListener();
  var id = ++_layerIdCounter;
  var entry = {
    layer: layer,
    id: id,
    _order: _layerHandlers.length,
    handlers: {
      escape: typeof handlers.escape === "function" ? handlers.escape : null,
      numpadAdd: typeof handlers.numpadAdd === "function" ? handlers.numpadAdd : null,
      numpadSubtract: typeof handlers.numpadSubtract === "function" ? handlers.numpadSubtract : null,
      onKeyDown: typeof handlers.onKeyDown === "function" ? handlers.onKeyDown : null,
    },
  };
  _layerHandlers.push(entry);
  return function unregister() {
    _layerHandlers = _layerHandlers.filter(function (e) { return e.id !== id; });
    // Remove the global document listener when the last handler unregisters
    _removeLayerListenerIfEmpty();
  };
}

/**
 * Remove all layer handlers (cleanup on destroy).
 */
export function clearAllLayerHandlers() {
  _layerHandlers = [];
  _removeLayerListenerIfEmpty();
}

/**
 * Get the current highest-layer escape handler that would fire (for testing).
 * @returns {number|null} The layer number that would handle Escape, or null.
 */
export function getActiveEscapeLayer() {
  if (document.fullscreenElement) return 5;
  var sorted = _layerHandlers.slice().sort(function (a, b) {
    if (b.layer !== a.layer) return b.layer - a.layer;
    return b._order - a._order;
  });
  for (var i = 0; i < sorted.length; i++) {
    if (typeof sorted[i].handlers.escape === "function") return sorted[i].layer;
  }
  return null;
}

// ── Element helper ────────────────────────────────────────────────────────

export function el(tag, props = {}, children = []) {
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
    } else if (k === "disabled" || k === "checked" || k === "hidden" || k === "readonly" || k === "required") {
      // Boolean HTML attributes must use the DOM property, not setAttribute,
      // because setAttribute("disabled", false) sets disabled="false" which still disables.
      if (props[k]) e.setAttribute(k, "");
      else e.removeAttribute(k);
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

// ── Status badge helper ──────────────────────────────────────────────────

export function statusBadge(text, kind) {
  const cls = kind === "ok" ? "comfymodal-studio-status-badge ok"
    : kind === "warn" ? "comfymodal-studio-status-badge warn"
    : kind === "error" ? "comfymodal-studio-status-badge error"
    : "comfymodal-studio-status-badge neutral";
  return el("span", { class: cls, text: text });
}

// ── Legacy empty state renderer ──────────────────────────────────────────
// Kept for backward compatibility with tests that reference it from the
// backend module.

/**
 * Create a zoomable image element with accessible zoom controls
 * and fullscreen support.
 * Returns a { container, updateZoom } object.
 * - container: DOM element wrapping the image + zoom toolbar
 * - updateZoom: function(newZoom) to programmatically set zoom
 */
export function createZoomableImageEl(imageUrl, alt) {
  var zoomLevel = 1;
  var fitMode = true;
  var isFullscreen = false;
  var _layerUnreg = null;
  var _destroyed = false;

  var container = document.createElement("div");
  container.className = "comfymodal-studio-zoom-wrap";
  container.setAttribute("data-testid", "zoomable-image");

  var imgContainer = document.createElement("div");
  imgContainer.className = "comfymodal-studio-zoom-image-container";

  var img = document.createElement("img");
  img.src = imageUrl;
  img.alt = alt || "Zoomable image";
  img.draggable = false;
  imgContainer.appendChild(img);

  var controls = document.createElement("div");
  controls.className = "comfymodal-studio-zoom-controls";
  controls.setAttribute("role", "toolbar");
  controls.setAttribute("aria-label", "Image zoom controls");

  function _zoomIn() {
    fitMode = false;
    zoomLevel = Math.min(8, zoomLevel + 0.25);
    _applyZoom();
  }

  function _zoomOut() {
    fitMode = false;
    zoomLevel = Math.max(0.25, zoomLevel - 0.25);
    _applyZoom();
  }

  function _zoomReset() {
    fitMode = true;
    zoomLevel = 1;
    _applyZoom();
  }

  function _applyZoom() {
    if (fitMode) {
      img.style.transform = "";
      img.style.maxWidth = "100%";
      img.style.maxHeight = "80vh";
      zoomLabel.textContent = "Fit";
      fitBtn.classList.add("fit-active");
    } else {
      img.style.transform = "scale(" + zoomLevel + ")";
      img.style.maxWidth = "none";
      img.style.maxHeight = "none";
      zoomLabel.textContent = Math.round(zoomLevel * 100) + "%";
      fitBtn.classList.remove("fit-active");
    }
  }

  function _toggleFullscreen() {
    if (isFullscreen) {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    } else {
      var fsTarget = container;
      if (fsTarget.requestFullscreen) {
        fsTarget.requestFullscreen();
      }
    }
  }

  function _onFullscreenChange() {
    if (_destroyed) return;
    isFullscreen = !!document.fullscreenElement;
    if (isFullscreen) {
      fullscreenBtn.textContent = "\u292b";
      fullscreenBtn.setAttribute("aria-label", "Exit fullscreen");
      fullscreenBtn.classList.add("fullscreen-active");
      // Re-apply zoom in fullscreen context
      _applyZoom();
    } else {
      fullscreenBtn.textContent = "\u26f6";
      fullscreenBtn.setAttribute("aria-label", "Fullscreen");
      fullscreenBtn.classList.remove("fullscreen-active");
      // Restore normal zoom
      _applyZoom();
    }
  }

  // Layer 4: zoom control
  _layerUnreg = registerLayerHandler(4, {
    escape: function () {
      // If zoomed in (not fit mode), reset to fit
      if (!fitMode) {
        _zoomReset();
        return true;
      }
      return false; // let preview/dialog handle it
    },
    numpadAdd: function () {
      _zoomIn();
      return true;
    },
    numpadSubtract: function () {
      _zoomOut();
      return true;
    },
  });

  document.addEventListener("fullscreenchange", _onFullscreenChange);

  var zoomOutBtn = document.createElement("button");
  zoomOutBtn.className = "comfymodal-studio-zoom-btn";
  zoomOutBtn.textContent = "\u2212";  // −
  zoomOutBtn.setAttribute("data-testid", "zoom-out");
  zoomOutBtn.setAttribute("aria-label", "Zoom out");
  zoomOutBtn.addEventListener("click", _zoomOut);

  var zoomInBtn = document.createElement("button");
  zoomInBtn.className = "comfymodal-studio-zoom-btn";
  zoomInBtn.textContent = "+";
  zoomInBtn.setAttribute("data-testid", "zoom-in");
  zoomInBtn.setAttribute("aria-label", "Zoom in");
  zoomInBtn.addEventListener("click", _zoomIn);

  var fitBtn = document.createElement("button");
  fitBtn.className = "comfymodal-studio-zoom-btn fit-active";
  fitBtn.textContent = "\u26f6";  // ⛶
  fitBtn.setAttribute("data-testid", "zoom-fit");
  fitBtn.setAttribute("aria-label", "Fit to viewport");
  fitBtn.addEventListener("click", _zoomReset);

  var fullscreenBtn = document.createElement("button");
  fullscreenBtn.className = "comfymodal-studio-zoom-btn";
  fullscreenBtn.textContent = "\u26f6";
  fullscreenBtn.setAttribute("data-testid", "zoom-fullscreen");
  fullscreenBtn.setAttribute("aria-label", "Fullscreen");
  fullscreenBtn.addEventListener("click", _toggleFullscreen);
  fullscreenBtn.style.fontSize = "13px";

  var zoomLabel = document.createElement("span");
  zoomLabel.className = "comfymodal-studio-zoom-label";
  zoomLabel.textContent = "Fit";
  zoomLabel.setAttribute("data-testid", "zoom-label");
  zoomLabel.setAttribute("aria-live", "polite");

  controls.appendChild(zoomOutBtn);
  controls.appendChild(zoomInBtn);
  controls.appendChild(fitBtn);
  controls.appendChild(fullscreenBtn);
  controls.appendChild(zoomLabel);
  container.appendChild(imgContainer);
  container.appendChild(controls);

  // Keyboard support on the image container (Ctrl shortcuts, fullscreen toggle)
  imgContainer.addEventListener("keydown", function (e) {
    // Ctrl++ / Ctrl+= zoom in
    if ((e.ctrlKey || e.metaKey) && (e.key === "=" || e.key === "+")) {
      e.preventDefault();
      _zoomIn();
      return;
    }
    // Ctrl+- zoom out
    if ((e.ctrlKey || e.metaKey) && (e.key === "-" || e.key === "\u2212")) {
      e.preventDefault();
      _zoomOut();
      return;
    }
    // Ctrl+0 / R reset
    if ((e.ctrlKey || e.metaKey) && e.key === "0") {
      e.preventDefault();
      _zoomReset();
      return;
    }
    if (e.key === "r" || e.key === "R") {
      // Only without ctrl/meta to avoid browser reload conflicts
      if (!e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        _zoomReset();
      }
    }
    // F / F11 for fullscreen toggle
    if (e.key === "f" || e.key === "F" || e.key === "F11") {
      if (!e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        _toggleFullscreen();
      }
    }
  });

  // Make image container keyboard-focusable so zoom shortcuts (Ctrl++/Ctrl+-/R)
  // are reachable via Tab. Escape and Tab-cycle still bubble to the preview overlay.
  imgContainer.setAttribute("tabindex", "0");

  /**
   * Destroy: clean up layer registry and fullscreenchange listener.
   */
  function _destroy() {
    _destroyed = true;
    if (_layerUnreg) {
      _layerUnreg();
      _layerUnreg = null;
    }
    document.removeEventListener("fullscreenchange", _onFullscreenChange);
  }

  return {
    container: container,
    updateZoom: function (z) {
      if (z == null || z === "fit") {
        _zoomReset();
      } else {
        fitMode = false;
        zoomLevel = Math.max(0.25, Math.min(8, Number(z) || 1));
        _applyZoom();
      }
    },
    destroy: _destroy,
  };
}

/**
 * Create a shared image preview overlay with zoomable image and
 * configurable info sections. Used by both experiment cell detail
 * and history preview to provide a consistent viewing experience.
 *
 * @param {object} opts
 * @param {string|null}  opts.imageUrl      - Image URL or null for no-image state
 * @param {string}       opts.alt           - Alt text for the image
 * @param {function}     opts.onClose       - Called when overlay should close
 * @param {function}     [opts.onKeyDown]   - Called for every keydown (after Escape/numpad checks), receives KeyboardEvent, return true to consume
 * @param {Array<HTMLElement>} [opts.sections] - DOM elements rendered below the image
 * @param {boolean}      [opts.focusTrap]   - Enable Tab/Shift+Tab focus trap
 * @returns {{ overlay: HTMLElement, close: function, contentEl: HTMLElement }}
 */
export function createImagePreviewOverlay(opts) {
  var overlay = document.createElement("div");
  overlay.className = "comfymodal-studio-preview-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", opts.alt || "Image preview");

  var _layerUnreg = null;
  var _zoomObj = null;
  var _closed = false;

  // Backdrop — click to close
  var backdrop = document.createElement("div");
  backdrop.className = "comfymodal-studio-preview-overlay-backdrop";
  overlay.appendChild(backdrop);

  // Content wrapper
  var content = document.createElement("div");
  content.className = "comfymodal-studio-preview-overlay-content";

  // ── Top toolbar: close + download ──────────────────────────────────
  var toolbar = document.createElement("div");
  toolbar.className = "comfymodal-studio-preview-toolbar";
  toolbar.style.cssText = "display:flex;align-items:center;gap:6px;justify-content:flex-end;padding:4px 8px;flex-shrink:0;";

  // Close button
  var closeBtn = document.createElement("button");
  closeBtn.className = "comfymodal-studio-preview-overlay-close";
  closeBtn.setAttribute("aria-label", "Close preview");
  closeBtn.textContent = "\u00d7";
  closeBtn.style.cssText = "background:transparent;border:none;color:#aaa;font-size:20px;cursor:pointer;line-height:1;padding:2px 6px;";
  closeBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    close();
  });
  toolbar.appendChild(closeBtn);

  // Download button (only when image URL is present)
  if (opts.imageUrl) {
    (function () {
      var dlBtn = document.createElement("button");
      dlBtn.className = "comfymodal-studio-download-btn";
      dlBtn.setAttribute("aria-label", "Download image");
      dlBtn.textContent = "\u2b07";
      dlBtn.title = "Download image";
      dlBtn.style.cssText = "background:transparent;border:none;color:#aaa;font-size:16px;cursor:pointer;line-height:1;padding:2px 6px;";

      // Sanitize filename from available metadata
      function _getFilename() {
        var meta = opts.metadata || {};
        var candidates = [
          meta.filename,
          meta.output_path,
          meta.primary_asset_id,
          meta.prompt,
          opts.alt,
        ];
        for (var i = 0; i < candidates.length; i++) {
          if (candidates[i] && typeof candidates[i] === "string" && candidates[i].length > 0) {
            // Extract basename, strip extension, sanitize
            var base = candidates[i].split("/").pop().split("\\").pop();
            base = base.replace(/\.[^.]+$/, ""); // remove extension
            // Keep only alphanumeric, dash, underscore, dot
            base = base.replace(/[^a-zA-Z0-9_-]/g, "_").substring(0, 100);
            if (base.length > 0) return base;
          }
        }
        return "modal-image";
      }

      dlBtn.addEventListener("click", async function (e) {
        e.stopPropagation();
        dlBtn.disabled = true;
        dlBtn.textContent = "\u23f3";
        try {
          var resp = await fetch(opts.imageUrl);
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          var blob = await resp.blob();
          var ext = (blob.type.split("/")[1] || "png").replace(/[^a-zA-Z0-9]/g, "");
          var filename = _getFilename() + "." + ext;
          var objUrl = URL.createObjectURL(blob);
          var a = document.createElement("a");
          a.href = objUrl;
          a.download = filename;
          // Safe anchor download: no navigation, revoke after triggering
          document.body.appendChild(a);
          a.click();
          setTimeout(function () {
            if (a.parentNode) a.parentNode.removeChild(a);
            URL.revokeObjectURL(objUrl);
          }, 100);
        } catch (err) {
          var errEl = document.createElement("span");
          errEl.textContent = "Download failed";
          errEl.style.cssText = "color:#f87171;font-size:11px;margin-left:4px;";
          toolbar.appendChild(errEl);
          setTimeout(function () { if (errEl.parentNode) errEl.remove(); }, 3000);
        } finally {
          dlBtn.disabled = false;
          dlBtn.textContent = "\u2b07";
        }
      });

      toolbar.appendChild(dlBtn);
    })();
  }

  content.appendChild(toolbar);

  // Zoomable image or no-image placeholder
  if (opts.imageUrl) {
    _zoomObj = createZoomableImageEl(opts.imageUrl, opts.alt);
    content.appendChild(_zoomObj.container);
  } else {
    var noImg = document.createElement("div");
    noImg.className = "comfymodal-studio-preview-overlay-noimage";
    noImg.textContent = "No image available";
    content.appendChild(noImg);
  }

  // Custom sections below the image
  if (opts.sections && opts.sections.length > 0) {
    var sectionsWrap = document.createElement("div");
    sectionsWrap.className = "comfymodal-studio-preview-overlay-sections";
    for (var si = 0; si < opts.sections.length; si++) {
      sectionsWrap.appendChild(opts.sections[si]);
    }
    content.appendChild(sectionsWrap);
  }

  overlay.appendChild(content);

  // Layer 3: preview overlay Escape + arrow-navigation handler
  _layerUnreg = registerLayerHandler(3, {
    escape: function () {
      close();
      return true;
    },
    onKeyDown: typeof opts.onKeyDown === "function" ? opts.onKeyDown : null,
  });

  // Backdrop click to close
  backdrop.addEventListener("click", function () {
    close();
  });

  // Focus trap: Tab/Shift+Tab cycle within the overlay (on overlay keydown)
  overlay.addEventListener("keydown", function (e) {
    if (opts.focusTrap && e.key === "Tab") {
      var focusable = overlay.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
  });

  function close() {
    // Idempotent: only run once.  All internal paths (Escape handler,
    // backdrop click, close button) call close(), and external callers
    // may also call preview.close().  The _closed guard ensures exactly
    // one execution of cleanup and the onClose callback.
    if (_closed) return;
    _closed = true;

    // Clean up layer handler (removes from registry)
    if (_layerUnreg) {
      _layerUnreg();
      _layerUnreg = null;
    }
    // Clean up zoomable image (removes fullscreenchange listener, layer handler)
    if (_zoomObj && typeof _zoomObj.destroy === "function") {
      _zoomObj.destroy();
      _zoomObj = null;
    }
    if (overlay.parentNode) {
      overlay.remove();
    }
    // Notify the caller after cleanup so the callback can safely
    // re-render or restore focus without stale layer entries.
    if (typeof opts.onClose === "function") {
      opts.onClose();
    }
  }

  return { overlay: overlay, close: close, contentEl: content };
}

export function renderEmptyState(listContent, detailPanel, context, state) {
  while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
  const emptyCard = el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No backends configured via legacy discovery.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: "Use the Snapshots or Backend Presets tabs above.", style: "font-size:12px;color:#555;margin:0 0 8px;" }),
  ]);
  while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
  listContent.appendChild(emptyCard);
}
