// Modal Studio — Shared UI Helpers
//
// Element builder, status badges, and legacy empty state renderer shared
// across Backend page modules.

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

  // Keyboard support on the image container
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

  // Backdrop — click to close
  var backdrop = document.createElement("div");
  backdrop.className = "comfymodal-studio-preview-overlay-backdrop";
  overlay.appendChild(backdrop);

  // Content wrapper
  var content = document.createElement("div");
  content.className = "comfymodal-studio-preview-overlay-content";

  // Close button
  var closeBtn = document.createElement("button");
  closeBtn.className = "comfymodal-studio-preview-overlay-close";
  closeBtn.setAttribute("aria-label", "Close preview");
  closeBtn.textContent = "\u00d7";
  closeBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    opts.onClose();
  });
  content.appendChild(closeBtn);

  // Zoomable image or no-image placeholder
  if (opts.imageUrl) {
    var zoomImg = createZoomableImageEl(opts.imageUrl, opts.alt);
    content.appendChild(zoomImg.container);
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

  // Backdrop click to close
  backdrop.addEventListener("click", function () {
    opts.onClose();
  });

  // Escape to close (does not conflict with zoom shortcuts which use Ctrl+)
  overlay.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      e.stopPropagation();
      opts.onClose();
      return;
    }
    // Focus trap: Tab/Shift+Tab cycle within the overlay
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
    if (overlay.parentNode) {
      overlay.remove();
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
