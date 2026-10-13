// Modal Studio — Shared UI Helpers
//
// Element builder, status badges (shared chip base), keyboard registry,
// zoomable image preview, image preview overlay, download button, and the
// generic empty-state primitive shared across Backend page modules.

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
let _fullscreenExitFallbackTimer = null;

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
      if (_fullscreenExitFallbackTimer) clearTimeout(_fullscreenExitFallbackTimer);
      _fullscreenExitFallbackTimer = setTimeout(function () {
        _fullscreenExitFallbackTimer = null;
        if (_fullscreenExitPending && document.fullscreenElement) {
          _fullscreenExitPending = false;
          _dispatchLayerEvent("escape", {
            preventDefault: function () {},
            stopPropagation: function () {},
          });
        }
      }, 300);
      // Don't consume — let browser's native handler exit fullscreen.
      // The fullscreenchange event will clear _fullscreenExitPending.
      return;
    }
    _fullscreenExitPending = false;
    if (_fullscreenExitFallbackTimer) {
      clearTimeout(_fullscreenExitFallbackTimer);
      _fullscreenExitFallbackTimer = null;
    }
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
    if (_fullscreenExitFallbackTimer) {
      clearTimeout(_fullscreenExitFallbackTimer);
      _fullscreenExitFallbackTimer = null;
    }
  }
}

function _onFullscreenChangeGlobal() {
  // Clear the pending flag when fullscreen exits so the next Escape
  // keydown goes through normal layer dispatch.
  if (!document.fullscreenElement) {
    _fullscreenExitPending = false;
    if (_fullscreenExitFallbackTimer) {
      clearTimeout(_fullscreenExitFallbackTimer);
      _fullscreenExitFallbackTimer = null;
    }
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

function _timingNumber(value) {
  if (value == null || value === "") return null;
  var number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function _timingDuration(value) {
  var number = _timingNumber(value);
  if (number == null) return "";
  if (number < 1000) return Math.round(number) + "ms";
  return (number / 1000).toFixed(number >= 10000 ? 1 : 2).replace(/\.0+$/, "") + "s";
}

// The viewer shows exactly 7 pipeline buckets with human names.  Golden
// telemetry, legacy canonical fields, and stages arrays all funnel here:
// flat keys are summed per bucket, stages[] entries are mapped by label
// into the same buckets (used only when no flat key fed that bucket, so a
// record carrying both shapes is never double-counted).  End-to-end/total
// is returned separately for the section header — never as a flow node.
var _TIMING_BUCKETS = [
  { key: "restore", label: "Restore", group: "restore",
    flat: ["golden_restore", "golden_request_setup", "restore_total_ms", "platform_pre_restore_ms", "studio_queue_ms", "queue_ms", "t0_to_t1"] },
  { key: "clip-load", label: "CLIP load", group: "clip",
    flat: ["golden_clip_load", "clip_load_ms", "clip_load", "model_load_ms"] },
  { key: "clip-forward", label: "CLIP forward", group: "clip-unet",
    flat: ["golden_clip_forward", "clip_encode_ms", "clip_encode", "clip_forward_ms"] },
  { key: "unet-load", label: "UNET load", group: "clip-unet",
    flat: ["golden_unet_load", "unet_load_ms"] },
  { key: "sampling", label: "Sampling", group: "sampling-vae",
    flat: ["golden_sampler_prepare", "golden_sampling", "golden_sampler_tail", "sampling_ms", "sampler", "sampler_prepare_ms", "sampler_tail_ms"] },
  { key: "vae-load", label: "VAE load", group: "sampling-vae",
    flat: ["golden_vae_load", "vae_load_ms"] },
  { key: "output", label: "Output", group: "output",
    flat: ["golden_vae_decode", "golden_output", "golden_teardown", "golden_durable_commit", "vae_decode_ms", "vae_decode", "image_io_ms", "output_transfer_ms", "image_io", "local_output_materialization_ms", "history_finalization_ms"] },
];

var _TIMING_TOTAL_KEYS = ["end_to_end_total_ms", "endToEndMs", "total_ms", "modal_to_browser"];

function _timingStageDuration(stage) {
  if (!stage || typeof stage !== "object") return null;
  var raw = stage.durationMs != null ? stage.durationMs
    : stage.duration_ms != null ? stage.duration_ms
    : stage.value != null ? stage.value
    : stage.ms != null ? stage.ms : null;
  return _timingNumber(raw);
}

// Map a stages[] label onto a bucket key.  Returns "total" for the
// end-to-end rollup (header only), a bucket key, or null to skip
// (overlapping parent intervals like Request/Scheduler Execution and
// Validation must never inflate a bucket).
function _timingBucketForLabel(label) {
  var text = String(label == null ? "" : label).toLowerCase().replace(/[_-]+/g, " ");
  if (!text) return null;
  if (text.indexOf("end to end") !== -1 || text === "total" || text.indexOf("endtoend") !== -1) return "total";
  if (text.indexOf("restore") !== -1 || text.indexOf("request setup") !== -1 || text.indexOf("queue") !== -1
    || text.indexOf("preparation") !== -1 || text.indexOf("pre restore") !== -1 || text.indexOf("prerestore") !== -1
    || text.indexOf("snapshot") !== -1 || text.indexOf("runtime restore") !== -1) return "restore";
  if (text.indexOf("clip forward") !== -1 || text.indexOf("prompt encod") !== -1 || text.indexOf("clip encode") !== -1) return "clip-forward";
  if (text.indexOf("clip load") !== -1 || text.indexOf("model / clip") !== -1 || text.indexOf("model load") !== -1
    || (text.indexOf("clip") !== -1 && text.indexOf("load") !== -1)) return "clip-load";
  if (text.indexOf("unet") !== -1) return "unet-load";
  if (text.indexOf("sampl") !== -1) return "sampling";
  if (text.indexOf("vae load") !== -1) return "vae-load";
  if (text.indexOf("vae decode") !== -1 || text.indexOf("decode") !== -1 || text.indexOf("output") !== -1
    || text.indexOf("image") !== -1 || text.indexOf("delivery") !== -1 || text.indexOf("materialization") !== -1
    || text.indexOf("finalization") !== -1 || text.indexOf("teardown") !== -1 || text.indexOf("durable") !== -1) return "output";
  return null;
}

function _timingFlowEntries(timing) {
  var root = timing && typeof timing === "object" ? timing : {};
  if (Array.isArray(root)) root = { stages: root };
  var values = {};
  var flatSources = [root.timings, root.timing, root.rawTiming, root.timing_summary, root.timingSummary,
    root.deltas_ms, root.remote_timings, root.derived_ms];
  if (root.trace && typeof root.trace === "object") {
    flatSources.push(root.trace.deltas_ms, root.trace.derived_ms);
  }
  if (root.wall_clock_trace && typeof root.wall_clock_trace === "object") {
    flatSources.push(root.wall_clock_trace.post_sampler_summary);
  }
  flatSources.push(root);
  flatSources.forEach(function (source) {
    if (source && typeof source === "object" && !Array.isArray(source)) {
      Object.keys(source).forEach(function (k) {
        if (values[k] == null && source[k] != null) values[k] = source[k];
      });
    }
  });

  var stageLists = [];
  [root.timingStages, root.stages, root.timing_stages].forEach(function (list) {
    if (Array.isArray(list) && list.length > 0) stageLists.push(list);
  });
  [root.timings, root.timing, root.rawTiming].forEach(function (source) {
    if (source && typeof source === "object") {
      if (Array.isArray(source.stages) && source.stages.length > 0) stageLists.push(source.stages);
      if (Array.isArray(source.timingStages) && source.timingStages.length > 0) stageLists.push(source.timingStages);
    }
  });

  // End-to-end total for the header (never a node).
  var totalMs = null;
  for (var ti = 0; ti < _TIMING_TOTAL_KEYS.length; ti++) {
    var total = _timingNumber(values[_TIMING_TOTAL_KEYS[ti]]);
    if (total != null && total > 0) { totalMs = total; break; }
  }
  var stageTotal = null;
  var bucketStageSums = {};
  var unmatchedStages = [];
  stageLists.forEach(function (list) {
    list.forEach(function (stage) {
      var duration = _timingStageDuration(stage);
      if (duration == null) return;
      var bucket = _timingBucketForLabel(stage && stage.label);
      if (bucket === "total") {
        if (duration > 0 && (stageTotal == null || duration > stageTotal)) stageTotal = duration;
        return;
      }
      if (bucket) {
        bucketStageSums[bucket] = (bucketStageSums[bucket] || 0) + duration;
        return;
      }
      if (stage && stage.label != null) unmatchedStages.push({ label: String(stage.label), durationMs: duration });
    });
  });
  if (totalMs == null) totalMs = stageTotal;

  var entries = [];
  _TIMING_BUCKETS.forEach(function (bucket) {
    var sum = 0;
    var seen = false;
    bucket.flat.forEach(function (key) {
      var part = _timingNumber(values[key]);
      if (part != null) {
        seen = true;
        sum += part;
      }
    });
    // Stages-array values fill buckets the flat keys never fed, so a
    // record carrying both shapes is never double-counted.
    if (!seen && bucketStageSums[bucket.key] != null) {
      sum = bucketStageSums[bucket.key];
      seen = sum > 0;
    }
    if (seen && sum > 0) entries.push({ key: bucket.key, label: bucket.label, group: bucket.group, durationMs: sum });
  });

  // Last resort: the record carries timing data in shapes we do not model.
  // Show it humanized rather than claiming nothing was recorded.
  if (entries.length === 0 && unmatchedStages.length > 0) {
    unmatchedStages.slice(0, 7).forEach(function (stage, index) {
      var human = stage.label.replace(/^golden[_ ]+/i, "").replace(/[_-]+/g, " ").trim();
      human = human.charAt(0).toUpperCase() + human.slice(1);
      entries.push({ key: "stage-" + index, label: human || stage.label, group: "legacy-" + index, durationMs: stage.durationMs });
    });
  }
  return { entries: entries, totalMs: totalMs };
}

export function renderTimingFlow(timing, options = {}) {
  var flow = _timingFlowEntries(timing);
  var entries = flow.entries;
  var sectionClass = options.sectionClass || "comfymodal-studio-timing-flow-section";
  var section = el("div", {
    class: sectionClass,
    "data-testid": options.testid || "timing-flow",
  }, [el("div", {
    class: "comfymodal-studio-timing-flow-title",
    text: options.title || (flow.totalMs != null ? "Timing \u00b7 " + _timingDuration(flow.totalMs) : "Timing"),
  })]);

  // Compat row: legacy suites pin the end-to-end total via the row-key
  // class.  It lives in the header so the flow itself stays 7 nodes.
  if (flow.totalMs != null) {
    section.appendChild(el("div", { class: "comfymodal-studio-timing-flow-total" }, [
      el("span", {     class: "comfymodal-studio-viewer-row-key", text: "End-to-End Total" }),
      el("span", {     class: "comfymodal-studio-viewer-row-value", text: _timingDuration(flow.totalMs) }),
    ]));
  }
  if (entries.length === 0) {
    // Only reached when no timing source carried anything at all.
    section.appendChild(el("div", {
      class: "comfymodal-studio-viewer-placeholder",
      "data-testid": options.placeholderTestid || "viewer-timing-placeholder",
      text: "Diagnostics pending",
    }));
    return section;
  }

  var groups = [];
  entries.forEach(function (entry) {
    var group = groups.find(function (candidate) { return candidate.key === entry.group; });
    if (!group) {
      group = { key: entry.group, entries: [] };
      groups.push(group);
    }
    group.entries.push(entry);
  });
  var flow = el("div", {
    class: "comfymodal-studio-timing-flow",
    role: "list",
    "aria-label": "Generation timing flow",
  });
  groups.forEach(function (group, index) {
    var column = el("div", {
      class: "comfymodal-studio-timing-flow-column",
      role: "listitem",
    });
    group.entries.forEach(function (entry) {
      column.appendChild(el("div", {
        class: "comfymodal-studio-timing-flow-node",
        "data-stage": entry.key,
      }, [
        el("span", { class: "comfymodal-studio-viewer-row-key", text: entry.label }),
        el("span", { class: "comfymodal-studio-viewer-row-value", text: _timingDuration(entry.durationMs) }),
      ]));
    });
    flow.appendChild(column);
    if (index < groups.length - 1) {
      flow.appendChild(el("span", {
        class: "comfymodal-studio-timing-flow-arrow",
        "aria-hidden": "true",
        text: "→",
      }));
    }
  });
  section.appendChild(flow);
  return section;
}

// ── Status badge helper ──────────────────────────────────────────────────
//
// Phase I3: badges adopt the shared `.cm-chip` base + `data-tone` system
// while PRESERVING the legacy feature classes (`comfymodal-studio-status-badge`
// plus its kind modifier) that callers/CSS still rely on.  Tone mapping is
// truthful to the existing vocabulary: ok/warn/error pass through; every
// other kind (including "neutral") lands on the neutral tone.

const _STATUS_TONE_KINDS = ["ok", "warn", "error"];

export function statusBadge(text, kind) {
  const legacy = _STATUS_TONE_KINDS.indexOf(kind) !== -1 ? kind : "neutral";
  const tone = legacy;
  return el("span", {
    class: "comfymodal-studio-status-badge " + legacy + " cm-chip",
    "data-tone": tone,
    text: text,
  });
}

// ── Image viewer (generic foundation) ─────────────────────────────────────
//
// Phase I5 re-measurement: these two helpers have NO current production
// caller — the only import lives in studio-playground.js and is never
// invoked (orphaned by the H13/H18 deletions). The former doc claim that
// they were "used by both experiment cell detail and history preview" was
// stale and has been removed. They are retained as generic single-image
// viewing capability for that existing import; the Phase I5 A/B compare
// deliberately does NOT host inside them (their single-image pan/zoom
// transform architecture does not model two pixel-aligned clipped layers)
// and reuses only el() + registerLayerHandler instead.

/**
 * Create a zoomable image element with pointer-based pan, pointer-centered
 * wheel zoom, accessible zoom controls, and fullscreen support.
 * Returns a { container, updateZoom, destroy } object.
 * - container: DOM element wrapping the image + toolbar (below the image)
 * - updateZoom: function(newZoom) to programmatically set zoom
 *
 * @param {string} imageUrl
 * @param {string} [alt]
 * @param {object} [opts]
 * @param {Array<HTMLElement>} [opts.extraControls] - buttons prepended to
 *   the toolbar row (e.g. close / save), rendered below the image.
 */
export function createZoomableImageEl(imageUrl, alt, opts) {
  opts = opts || {};
  var zoomLevel = 1;
  var fitMode = true;
  var panX = 0;
  var panY = 0;
  var isFullscreen = false;
  var _layerUnreg = null;
  var _destroyed = false;

  // Drag state
  var _dragging = false;
  var _dragPointerId = null;
  var _dragStartX = 0;
  var _dragStartY = 0;
  var _dragPanX = 0;
  var _dragPanY = 0;
  var _dragMoved = false;

  // Fit-box size (image's untransformed rendered size)
  var _fitW = 0;
  var _fitH = 0;

  var container = document.createElement("div");
  container.className = "comfymodal-studio-zoom-wrap";
  container.setAttribute("data-testid", "zoomable-image");

  var imgContainer = document.createElement("div");
  imgContainer.className = "comfymodal-studio-zoom-image-container";
  imgContainer.style.cssText = "user-select:none;touch-action:none;cursor:default;";

  var img = document.createElement("img");
  img.src = imageUrl;
  img.alt = alt || "Zoomable image";
  img.draggable = false;
  // Transform transitions are disabled so pointer-drag panning and rapid
  // wheel zoom track the pointer without lag.
  img.style.transition = "none";
  imgContainer.appendChild(img);

  var controls = document.createElement("div");
  controls.className = "comfymodal-studio-zoom-controls";
  controls.setAttribute("role", "toolbar");
  controls.setAttribute("aria-label", "Image zoom controls");

  function _viewerCenter() {
    var r = imgContainer.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }

  function _refreshFitSize() {
    var prev = img.style.transform;
    img.style.transform = "";
    var r = img.getBoundingClientRect();
    img.style.transform = prev;
    _fitW = r.width || 0;
    _fitH = r.height || 0;
  }

  function _clampPan() {
    if (fitMode) {
      panX = 0;
      panY = 0;
      return;
    }
    var maxX = Math.max(0, (zoomLevel - 1) * _fitW / 2);
    var maxY = Math.max(0, (zoomLevel - 1) * _fitH / 2);
    panX = Math.max(-maxX, Math.min(maxX, panX));
    panY = Math.max(-maxY, Math.min(maxY, panY));
  }

  function _applyZoom() {
    // Single sizing contract (matches .comfymodal-studio-viewer-stage CSS):
    // the image always fills the stage width and caps at the stage height,
    // so small history previews render full-bleed like playground outputs
    // instead of a tiny centered thumbnail in a wide black stage.
    var _stageMaxH = "calc(90vh - 90px)";
    if (fitMode) {
      panX = 0;
      panY = 0;
      img.style.transform = "";
      img.style.width = "100%";
      img.style.height = "auto";
      img.style.maxWidth = "100%";
      img.style.maxHeight = _stageMaxH;
      zoomLabel.textContent = "Fit";
      fitBtn.classList.add("fit-active");
      imgContainer.style.cursor = "default";
      return;
    }
    img.style.width = "100%";
    img.style.height = "auto";
    img.style.maxWidth = "100%";
    img.style.maxHeight = _stageMaxH;
    img.style.transform = "translate(" + panX + "px," + panY + "px) scale(" + zoomLevel + ")";
    zoomLabel.textContent = Math.round(zoomLevel * 100) + "%";
    fitBtn.classList.remove("fit-active");
    imgContainer.style.cursor = _dragging ? "grabbing" : "grab";
  }

  function _setZoom(newLevel, clientX, clientY) {
    var target = Math.max(1, Math.min(8, newLevel));
    if (target <= 1.0001) {
      _zoomReset();
      return;
    }
    var oldLevel = fitMode ? 1 : zoomLevel;
    var wasFit = fitMode;
    fitMode = false;
    if (wasFit) {
      panX = 0;
      panY = 0;
    }
    if (clientX != null && clientY != null) {
      // Keep the image point under the pointer fixed.
      var vc = _viewerCenter();
      var ux = (clientX - vc.x - panX) / oldLevel;
      var uy = (clientY - vc.y - panY) / oldLevel;
      zoomLevel = target;
      panX = clientX - vc.x - target * ux;
      panY = clientY - vc.y - target * uy;
    } else {
      zoomLevel = target;
    }
    _clampPan();
    _applyZoom();
  }

  function _zoomIn() {
    _refreshFitSize();
    _setZoom((fitMode ? 1 : zoomLevel) + 0.25, null, null);
  }

  function _zoomOut() {
    _refreshFitSize();
    _setZoom((fitMode ? 1 : zoomLevel) - 0.25, null, null);
  }

  function _zoomReset() {
    fitMode = true;
    zoomLevel = 1;
    panX = 0;
    panY = 0;
    _applyZoom();
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
      _refreshFitSize();
      _applyZoom();
    } else {
      fullscreenBtn.textContent = "\u26f6";
      fullscreenBtn.setAttribute("aria-label", "Fullscreen");
      fullscreenBtn.classList.remove("fullscreen-active");
      _refreshFitSize();
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

  // ── Pointer pan (only when zoomed in) ────────────────────────────────
  function _onPointerDown(e) {
    if (fitMode) {
      _dragMoved = false;
      return;
    }
    _dragging = true;
    _dragMoved = false;
    _dragPointerId = e.pointerId;
    _dragStartX = e.clientX;
    _dragStartY = e.clientY;
    _dragPanX = panX;
    _dragPanY = panY;
    imgContainer.style.cursor = "grabbing";
    try {
      imgContainer.setPointerCapture(e.pointerId);
    } catch (err) { /* capture unsupported — drag still works within viewer */ }
  }

  function _onPointerMove(e) {
    if (!_dragging || e.pointerId !== _dragPointerId) return;
    if (Math.abs(e.clientX - _dragStartX) > 3 || Math.abs(e.clientY - _dragStartY) > 3) {
      _dragMoved = true;
    }
    panX = _dragPanX + (e.clientX - _dragStartX);
    panY = _dragPanY + (e.clientY - _dragStartY);
    _clampPan();
    _applyZoom();
  }

  function _onPointerUp(e) {
    if (!_dragging || e.pointerId !== _dragPointerId) return;
    _dragging = false;
    _dragPointerId = null;
    try {
      imgContainer.releasePointerCapture(e.pointerId);
    } catch (err) { /* already released */ }
    imgContainer.style.cursor = "grab";
  }

  imgContainer.addEventListener("pointerdown", _onPointerDown);
  imgContainer.addEventListener("pointermove", _onPointerMove);
  imgContainer.addEventListener("pointerup", _onPointerUp);
  imgContainer.addEventListener("pointercancel", _onPointerUp);

  imgContainer.addEventListener("click", function (e) {
    if (_dragMoved) {
      _dragMoved = false;
      return;
    }
    _refreshFitSize();
    var current = fitMode ? 1 : zoomLevel;
    _setZoom(current === 1 ? 2 : current * 1.35, e.clientX, e.clientY);
  });

  // ── Wheel: pointer-centered zoom, page scroll prevented only over viewer
  function _onWheel(e) {
    e.preventDefault();
    e.stopPropagation();
    _refreshFitSize();
    var factor = Math.pow(1.12, -e.deltaY / 100);
    _setZoom((fitMode ? 1 : zoomLevel) * factor, e.clientX, e.clientY);
  }

  imgContainer.addEventListener("wheel", _onWheel, { passive: false });

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

  // Extra toolbar controls (close / save / download) go BEFORE the zoom
  // buttons so the row reads: [close] [save] [-] [+] [fit] [fullscreen].
  (opts.extraControls || []).forEach(function (btn) {
    if (btn) controls.appendChild(btn);
  });
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

  img.addEventListener("load", function () {
    if (_destroyed) return;
    _refreshFitSize();
  });

  /**
   * Destroy: clean up layer registry, listeners, and pointer capture.
   */
  function _destroy() {
    _destroyed = true;
    if (_dragging && _dragPointerId != null) {
      try { imgContainer.releasePointerCapture(_dragPointerId); } catch (err) {}
      _dragging = false;
    }
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
        _refreshFitSize();
        _setZoom(Number(z) || 1, null, null);
      }
    },
    destroy: _destroy,
  };
}

// ── Shared viewer building blocks ───────────────────────────────────────
// The one viewer for every full-size output, mounted by whichever surface
// the user is on.  It is deliberately surface-agnostic: it knows nothing
// about History, the Playground, or where a record came from.  It renders
// ONE record contract (see buildSharedViewerOverlay) with one zoom stage,
// one card/accordion vocabulary, and one timing flow.

var _VIEWER_PARAM_ORDER = ["seed", "steps", "cfg", "guidance", "sampler", "scheduler", "denoise", "resolution"];
var _VIEWER_PARAM_SKIP = ["prompt", "negative_prompt", "negativePrompt", "width", "height"];

export function viewerValueText(v) {
  if (v == null || v === "") return "";
  if (typeof v === "object") { try { return JSON.stringify(v); } catch (err) { return String(v); } }
  return String(v);
}

export function viewerDateText(v) {
  if (!v) return "";
  var d = new Date(v);
  if (isNaN(d.getTime())) return String(v);
  try {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
      + ", " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" });
  } catch (err) {
    return String(v);
  }
}

export function viewerDurationText(v) {
  var n = Number(v);
  if (!Number.isFinite(n)) return "";
  return _timingDuration(n);
}

// Single "Resolution" field derived from width x height (or a precomposed
// resolution value). Width/height never render as separate params — they
// fold into this one viewer-content field alongside preview, file size,
// model used, and workflow used.
export function viewerResolutionText(source, record) {
  function num(v) {
    if (v == null || v === "") return null;
    var n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : null;
  }
  function pairText(w, h) {
    if (w != null && h != null) return w + " \u00d7 " + h;
    if (w != null) return String(w);
    if (h != null) return String(h);
    return "";
  }
  var s = source && typeof source === "object" ? source : {};
  var r = record && typeof record === "object" ? record : {};
  // Precomposed resolution wins when it is a non-empty string.
  var pre = [s.resolution, s.dimensions, r.resolution, r.dimensions];
  for (var i = 0; i < pre.length; i++) {
    var v = pre[i];
    if (typeof v === "string" && v.trim() !== "") return v.trim();
    if (Array.isArray(v) && v.length >= 2) {
      var aw = num(v[0]);
      var ah = num(v[1]);
      var at = pairText(aw, ah);
      if (at) return at;
    } else if (v && typeof v === "object") {
      var ow = num(v.width != null ? v.width : v.w);
      var oh = num(v.height != null ? v.height : v.h);
      var ot = pairText(ow, oh);
      if (ot) return ot;
    }
  }
  var w = num(s.width != null && s.width !== "" ? s.width : r.width);
  var h = num(s.height != null && s.height !== "" ? s.height : r.height);
  if (w == null && r.raw && typeof r.raw === "object") {
    if (w == null) w = num(r.raw.width);
    if (h == null) h = num(r.raw.height);
  }
  // Snapshot-less fallback: asset-measured dimensions projected on the
  // featured output / outputs (always available when an image exists).
  // Params still win — this only fills what the snapshot did not provide.
  if (w == null || h == null) {
    var feat = r.featuredOutput && typeof r.featuredOutput === "object" ? r.featuredOutput : {};
    if (w == null) w = num(feat.width);
    if (h == null) h = num(feat.height);
    var outs = Array.isArray(r.outputs) ? r.outputs : [];
    for (var k = 0; k < outs.length; k++) {
      var o = outs[k] || {};
      if (w == null) w = num(o.width);
      if (h == null) h = num(o.height);
      if (w != null && h != null) break;
    }
  }
  return pairText(w, h);
}

// Human-readable file size ("1.2 MB"). Returns "" when unknown so callers
// omit the row instead of fabricating a value.
export function viewerFileSizeText(bytes) {
  if (bytes == null || bytes === "") return "";
  var n = Number(bytes);
  if (!Number.isFinite(n) || n < 0) return "";
  if (n < 1024) return n + " B";
  var units = ["KB", "MB", "GB", "TB"];
  var u = -1;
  var f = n;
  while (f >= 1024 && u < units.length - 1) { f /= 1024; u += 1; }
  var rounded = f >= 100 ? Math.round(f) : Math.round(f * 10) / 10;
  return rounded + " " + units[u];
}

// First known file-size value on a viewer record (or its outputs), else "".
// Checks every shape a size can arrive in without inventing one.
export function viewerFileSizeValue(record) {
  var rec = record && typeof record === "object" ? record : {};
  var candidates = [
    rec.fileSize, rec.file_size, rec.fileSizeBytes, rec.file_size_bytes,
    rec.byteCount, rec.byte_count, rec.byteSize, rec.byte_size,
    rec.bytes, rec.size, rec.sizeBytes, rec.size_bytes,
  ];
  var feat = rec.featuredOutput && typeof rec.featuredOutput === "object" ? rec.featuredOutput : {};
  candidates.push(
    feat.fileSize, feat.file_size, feat.byteCount, feat.byte_count,
    feat.byteSize, feat.byte_size, feat.bytes, feat.size,
  );
  var outs = Array.isArray(rec.outputs) ? rec.outputs : [];
  for (var i = 0; i < outs.length; i++) {
    var o = outs[i] || {};
    candidates.push(o.fileSize, o.file_size, o.byteCount, o.byte_count, o.byte_size, o.bytes, o.size);
  }
  for (var j = 0; j < candidates.length; j++) {
    var v = candidates[j];
    if (v != null && v !== "") {
      var n = Number(v);
      if (Number.isFinite(n) && n >= 0) return n;
    }
  }
  return "";
}

// Merge every shape a run record can carry controls in: normalized
// requested/resolved controls, raw/extra controls, params, and flat
// top-level seed/steps/etc fields the feed normalizer may leave out.
export function viewerMergedParams(record) {
  var r = record || {};
  var raw = r.raw && typeof r.raw === "object" ? r.raw : {};
  var extra = raw.extra && typeof raw.extra === "object" ? raw.extra : {};
  var merged = {};
  [r.requestedControls, r.resolvedControls, r.controls, raw.controls, raw.resolved_controls,
    raw.params, extra.controls, extra.resolved_controls, extra.params, r.params].forEach(function (source) {
    if (source && typeof source === "object" && !Array.isArray(source)) {
      Object.keys(source).forEach(function (k) {
        if (merged[k] == null || merged[k] === "") merged[k] = source[k];
      });
    }
  });
  ["seed", "steps", "cfg", "guidance", "sampler", "scheduler", "denoise", "width", "height",
    "resolution", "dimensions",
    "prompt", "negative_prompt", "negativePrompt"].forEach(function (key) {
    if ((merged[key] == null || merged[key] === "") && r[key] != null && r[key] !== "") merged[key] = r[key];
    if ((merged[key] == null || merged[key] === "") && raw[key] != null && raw[key] !== "") merged[key] = raw[key];
    if ((merged[key] == null || merged[key] === "") && extra[key] != null && extra[key] !== "") merged[key] = extra[key];
  });
  // Embedded-file recovery (PNG prompt JSON on detail outputs): lowest
  // priority — every source above wins per key, so snapshot and control
  // values are never overridden by file-derived ones.
  var embeddedSources = [];
  var featOut = r.featuredOutput && typeof r.featuredOutput === "object" ? r.featuredOutput : {};
  [featOut].concat(Array.isArray(r.outputs) ? r.outputs : []).forEach(function (o) {
    var ep = o && typeof o === "object" ? (o.embeddedParams || o.embedded_params) : null;
    if (ep && typeof ep === "object" && !Array.isArray(ep)) embeddedSources.push(ep);
  });
  embeddedSources.forEach(function (source) {
    Object.keys(source).forEach(function (k) {
      if (merged[k] == null || merged[k] === "") merged[k] = source[k];
    });
  });
  return merged;
}

export function viewerFirst() {
  for (var i = 0; i < arguments.length; i++) {
    if (arguments[i] != null && arguments[i] !== "") return arguments[i];
  }
  return "";
}

// Base payload for "Use parameters as base": the run's prompt + sampler
// controls keyed by SHELF role (prompt, negative_prompt, seed, steps,
// guidance/cfg, sampler, scheduler, denoise, width, height) so the
// Playground can apply them through its normal validated shelf path. Only
// known non-empty values are included, so applying never blanks a field
// the run did not record. Width/height are numeric. Models/workflow are
// deliberately excluded: the shelf has no model picker and workflows are
// selected by identity, never by name.
export function viewerBasePayload(record) {
  var rec = record || {};
  var params = viewerMergedParams(rec);
  var out = {};
  function put(key, value) {
    if (value == null || value === "") return;
    out[key] = value;
  }
  put("prompt", viewerFirst(rec.prompt, params.prompt));
  put("negative_prompt", viewerFirst(
    rec.negativePrompt, rec.negative_prompt,
    params.negative_prompt, params.negativePrompt));
  put("seed", params.seed);
  put("steps", params.steps);
  var scale = viewerFirst(params.guidance, params.cfg);
  put("guidance", scale);
  put("cfg", scale);
  put("sampler", params.sampler);
  put("scheduler", params.scheduler);
  put("denoise", params.denoise);
  ["width", "height"].forEach(function (key) {
    var n = Number(params[key]);
    if (Number.isFinite(n) && n > 0) out[key] = n;
  });
  return out;
}

// Cropped prompt accordion: ~3 lines visible with a fade; click or
// Enter/Space expands to the full text. The header carries a Copy prompt
// button (copies the prompt text only) with transient Copied feedback.
export function buildViewerPromptAccordion(prompt, negative) {
  var wrap = el("div", { class: "comfymodal-studio-viewer-prompts" });
  var copyBtn = el("button", {
    class: "comfymodal-secondary-btn comfymodal-studio-viewer-prompt-copy",
    type: "button",
    "data-testid": "viewer-prompt-copy",
    text: "Copy prompt",
    title: "Copy the prompt text",
  });
  copyBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    if (copyBtn.disabled) return;
    copyBtn.disabled = true;
    _copyTextToClipboard(String(prompt || ""), function (ok) {
      copyBtn.textContent = ok ? "Copied" : "Copy failed";
      setTimeout(function () {
        copyBtn.disabled = false;
        copyBtn.textContent = "Copy prompt";
      }, 1200);
    });
  });
  var value = el("div", {
    class: "comfymodal-studio-viewer-prompt-value",
    tabindex: "0",
    role: "button",
    "aria-expanded": "false",
    "aria-label": "Prompt (activate to expand)",
    "data-testid": "viewer-prompt",
  }, [
    el("span", { class: "comfymodal-studio-viewer-prompt-text", text: prompt || "" }),
    el("span", { class: "comfymodal-studio-viewer-prompt-fade", "aria-hidden": "true" }),
  ]);
  function toggle() {
    var expanded = value.getAttribute("aria-expanded") === "true";
    value.setAttribute("aria-expanded", expanded ? "false" : "true");
    value.classList.toggle("is-expanded", !expanded);
  }
  value.addEventListener("click", toggle);
  value.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
  });
  wrap.appendChild(el("div", { class: "comfymodal-studio-viewer-prompts-head" }, [
    el("div", { class: "comfymodal-studio-viewer-prompt-label", text: "Prompt" }),
    copyBtn,
  ]));
  wrap.appendChild(value);
  if (negative) {
    wrap.appendChild(el("div", { class: "comfymodal-studio-viewer-negative" }, [
      el("span", { class: "comfymodal-studio-viewer-prompt-label", text: "Negative prompt" }),
      el("div", { class: "comfymodal-studio-viewer-negative-text", text: String(negative) }),
    ]));
  }
  return wrap;
}

// Parameter grid.  The container (with its testid) always renders —
// prompts live in the accordion above, so they are skipped here.
export function buildViewerParamsGrid(params, testid, record) {
  var source = params && typeof params === "object" ? params : {};
  var items = [];
  _VIEWER_PARAM_ORDER.forEach(function (key) {
    if (key === "resolution") {
      var text = viewerResolutionText(source, record);
      if (text) {
        items.push(el("div", { class: "comfymodal-studio-viewer-param" }, [
          el("span", { class: "comfymodal-studio-viewer-param-key", text: "resolution" }),
          el("strong", { class: "comfymodal-studio-viewer-param-value", text: text }),
        ]));
      }
      return;
    }
    if (source[key] != null && source[key] !== "") {
      items.push(el("div", { class: "comfymodal-studio-viewer-param" }, [
        el("span", { class: "comfymodal-studio-viewer-param-key", text: key }),
        el("strong", { class: "comfymodal-studio-viewer-param-value", text: viewerValueText(source[key]) }),
      ]));
    }
  });
  Object.keys(source).forEach(function (key) {
    if (_VIEWER_PARAM_ORDER.indexOf(key) !== -1 || _VIEWER_PARAM_SKIP.indexOf(key) !== -1) return;
    if (source[key] != null && source[key] !== "") {
      items.push(el("div", { class: "comfymodal-studio-viewer-param" }, [
        el("span", { class: "comfymodal-studio-viewer-param-key", text: key }),
        el("strong", { class: "comfymodal-studio-viewer-param-value", text: viewerValueText(source[key]) }),
      ]));
    }
  });
  var grid = el("div", {
    class: "comfymodal-studio-preview-parameters comfymodal-studio-viewer-params",
    "data-testid": testid || "preview-parameters",
  }, [el("div", { class: "comfymodal-studio-preview-detail-label", text: "Parameters" })]);
  if (items.length > 0) {
    grid.appendChild(el("div", { class: "comfymodal-studio-viewer-params-grid" }, items));
  }
  return grid;
}

export function buildViewerCard(title, children, extraClass) {
  return el("section", {
    class: "comfymodal-studio-viewer-card" + (extraClass ? " " + extraClass : ""),
  }, [
    el("div", { class: "comfymodal-studio-viewer-card-title", text: title }),
  ].concat((children || []).filter(function (child) { return child != null; })));
}

// Collapsed accordion section (used for Metadata + embedded note editor).
export function buildViewerAccordion(title, children) {
  var body = el("div", { class: "comfymodal-studio-viewer-accordion-body" },
    (children || []).filter(function (child) { return child != null; }));
  var toggle = el("button", {
    type: "button",
    class: "comfymodal-studio-viewer-accordion-toggle",
    "aria-expanded": "false",
    text: title,
  });
  toggle.addEventListener("click", function () {
    var open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", open ? "false" : "true");
    body.hidden = open;
  });
  body.hidden = true;
  return el("section", {
    class: "comfymodal-studio-viewer-card comfymodal-studio-viewer-accordion",
  }, [toggle, body]);
}

// Pure layout assembler: zoom stage + right column + full-width timing.
// Fixed composition — callers pass data only (imageUrl, rightChildren,
// timing). No cosmetic opts.
export function buildViewerBody(opts = {}) {
  var body = el("div", { class: "comfymodal-studio-viewer-body" });
  var stage = el("div", { class: "comfymodal-studio-viewer-stage" });
  var right = el("div", {
    class: "comfymodal-studio-viewer-right",
    "data-testid": "preview-details",
  });
  if (opts.imageUrl) {
    stage.appendChild(createZoomableImageEl(opts.imageUrl, "Generated image", {}).container);
  } else {
    stage.appendChild(el("div", { class: "comfymodal-studio-preview-overlay-noimage", text: "No image available" }));
  }
  // Record-derived stage badges (fixed semantics, not a caller opt).
  (opts.stageBadges || []).forEach(function (child) { if (child) stage.appendChild(child); });
  (opts.rightChildren || []).forEach(function (child) { if (child) right.appendChild(child); });
  body.appendChild(stage);
  body.appendChild(right);
  body.appendChild(renderTimingFlow(opts.timing || {}, {
    sectionClass: "comfymodal-studio-viewer-timing",
    testid: "viewer-timing",
    placeholderTestid: "viewer-timing-placeholder",
  }));
  return body;
}

// Single choke point for every buildViewerShell mount. Both full-size
// surfaces (History detail, Playground preview) resolve a viewer through the
// shared resolveViewerInput and pass it through HERE — creation and
// re-render alike — so a new shell input is added once and can never drift
// between surfaces again. Pure data mapping (no DOM), unit-tested in Node.
//
// viewer:   a resolveViewerInput() result, or null/undefined pre-load (which
//           yields bare-body opts: no record, no image, no variant).
// adapters: behavioral only — { persistence, fileActions, onClose } —
//           passed through by reference, never reshaped.
export function resolveViewerShellArgs(viewer, adapters) {
  var v = viewer && typeof viewer === "object" ? viewer : {};
  var out = v.output && typeof v.output === "object" ? v.output : {};
  var a = adapters && typeof adapters === "object" ? adapters : {};
  var rec = v.record && typeof v.record === "object" ? v.record : {};
  var feat = rec.featuredOutput && typeof rec.featuredOutput === "object" ? rec.featuredOutput : {};
  var servedRaw = String(feat.servedVariant || feat.served_variant || "").toLowerCase();
  var served = servedRaw === "data_saver" || servedRaw === "datasaver" || servedRaw === "data-saver" || servedRaw === "preview"
    ? "Data Saver"
    : (servedRaw === "original" ? "Original" : "");
  var labelRaw = out.label ? String(out.label) : "";
  var labelNorm = /preview/i.test(labelRaw) ? "Data Saver" : labelRaw;
  var kindRaw = String(out.kind || "").toLowerCase();
  var kindNorm = (kindRaw === "data_saver" || kindRaw === "datasaver" || kindRaw === "data-saver" || kindRaw === "preview")
    ? "Data Saver"
    : (kindRaw === "original" ? "Original" : "");
  // The Variant row must describe the DISPLAYED bytes, which are picked by
  // the shared asset policy (label/kind) — backend served_variant is only a
  // last resort, because it can disagree with the policy (e.g. served
  // "original" on a record whose policy selection is the data-saver
  // preview, which is what the zoom stage actually shows).
  var variant = labelNorm || kindNorm || served;
  // Format of the DISPLAYED bytes, not the stored primary: data-saver
  // display is usually webp while the retained original is png.
  var format = variant === "Data Saver"
    ? (feat.dataSaverFormat || feat.data_saver_format || feat.preview_format || feat.format || "")
    : (variant === "Original"
      ? (feat.originalFormat || feat.original_format || feat.format || "")
      : (feat.format || ""));
  // File size of the DISPLAYED bytes (data-saver vs original differ).
  var fileSize = variant === "Data Saver"
    ? (feat.dataSaverByteSize != null ? feat.dataSaverByteSize : (feat.data_saver_byte_size != null ? feat.data_saver_byte_size : ""))
    : (variant === "Original"
      ? (feat.originalByteSize != null ? feat.originalByteSize : (feat.original_byte_size != null ? feat.original_byte_size : ""))
      : "");
  return {
    record: v.record,
    imageUrl: v.imageUrl,
    timing: v.timing,
    variant: variant,
    format: format,
    fileSize: fileSize,
    fileActions: a.fileActions != null ? a.fileActions : null,
    onUseAsBase: typeof a.onUseAsBase === "function" ? a.onUseAsBase : null,
    persistence: a.persistence,
    onClose: a.onClose,
  };
}

// Full overlay shell (backdrop + content + close + viewer body) with
// Escape/backdrop close and invoker focus restore.
// Callers pass DATA only: { record, imageUrl, timing, persistence }.
// There are no cosmetic opts: the fav star, note editor, and timing section
// are fixed in buildSharedViewerOverlay so Playground and History cannot
// drift apart. `persistence` is behavioral, not cosmetic:
// { setFavorite(record, next), setNote(record, text), onChanged() }.
export function buildViewerShell(opts = {}) {
  var overlay = el("div", {
    class: "comfymodal-studio-viewer-overlay",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": "Image preview",
  });
  var backdrop = el("div", { class: "comfymodal-studio-viewer-backdrop" });
  overlay.appendChild(backdrop);
  var content = el("div", {
    class: "comfymodal-studio-viewer-content",
  });
  var closeBtn = el("button", {
    class: "comfymodal-studio-viewer-close",
    type: "button",
    "aria-label": "Close",
    text: "\u00d7",
  });
  content.appendChild(closeBtn);
  var invoker = (function () {
    var ae = document.activeElement;
    return ae && typeof ae.focus === "function" && ae !== document.body ? ae : null;
  })();
  var closed = false;
  var layerUnreg = null;
  function close() {
    if (closed) return;
    closed = true;
    if (layerUnreg) { layerUnreg(); layerUnreg = null; }
    if (overlay.parentNode) overlay.remove();
    if (invoker && typeof invoker.focus === "function" && invoker.isConnected) {
      try { invoker.focus(); } catch (err) { /* detached */ }
    }
    if (typeof opts.onClose === "function") opts.onClose();
  }
  closeBtn.addEventListener("click", function () { close(); });
  backdrop.addEventListener("click", function () { close(); });
  layerUnreg = registerLayerHandler(3, {
    escape: function () { close(); return true; },
  });
  // A record produces the full shared composition (Run / Run Data /
  // Metadata + timing); without one the shell mounts a bare body.
  // `variant` is data (the displayed image's Preview/Original/Thumbnail
  // label from the shared asset policy), not cosmetic: it renders the
  // always-visible Variant row so the viewer answers "is this a preview?".
  // The overlay's onClose is the shell's own close (DOM removal + surface
  // cleanup + user onClose, idempotent) so the Delete button can dismiss
  // the modal after a successful delete on either surface.
  content.appendChild(opts.record ? buildSharedViewerOverlay({
    record: opts.record,
    imageUrl: opts.imageUrl,
    timing: opts.timing,
    variant: opts.variant,
    format: opts.format,
    fileSize: opts.fileSize,
    fileActions: opts.fileActions,
    persistence: opts.persistence,
    onClose: close,
  }) : buildViewerBody(opts));
  overlay.appendChild(content);

  function renderRecord(record, overrides) {
    var extra = overrides || {};
    var renderOpts = {
      record: record,
      imageUrl: extra.imageUrl != null ? extra.imageUrl : opts.imageUrl,
      timing: extra.timing != null ? extra.timing : opts.timing,
      variant: extra.variant != null ? extra.variant : opts.variant,
      format: extra.format != null ? extra.format : opts.format,
      fileSize: extra.fileSize != null ? extra.fileSize : opts.fileSize,
      fileActions: extra.fileActions != null ? extra.fileActions : opts.fileActions,
      onUseAsBase: extra.onUseAsBase != null ? extra.onUseAsBase : opts.onUseAsBase,
      persistence: opts.persistence,
      onClose: close,
    };
    while (content.firstChild) content.removeChild(content.firstChild);
    content.appendChild(closeBtn);
    content.appendChild(buildSharedViewerOverlay(renderOpts));
  }

  return {
    overlay: overlay,
    close: close,
    render: renderRecord,
    contentEl: content,
    closeButton: closeBtn,
    backdrop: backdrop,
  };
}

// The one viewer composition used by every full-size output surface.
// Callers pass DATA only: an already-resolved record plus imageUrl/timing,
// an optional `variant` label (the displayed image's Preview/Original/
// Thumbnail kind from the shared asset policy), an optional `fileActions`
// adapter ({ openAsset(assetId), revealAsset(assetId) }) for the File row's
// native buttons, an optional `onUseAsBase(payload)` callback for the Run
// Data "Use parameters as base" button, and an optional behavioral
// `persistence` adapter
// ({ setFavorite(record, next), setNote(record, text), onChanged() }).
// The fav star, note editor, params grid, and timing section are fixed here —
// there are no cosmetic opts — so no surface can drift apart from another.
//
// Record contract (neutral — no surface's vocabulary): { status, startedAt,
// completedAt, durationMs, runId, id, workflow, workflowVersion, prompt,
// negativePrompt, controls, models[], tags[], favorite, note,
// resolution/width/height, file size aliases, fullRenderFailed, timing }.
// Viewer-content fields: preview (zoom stage imageUrl), variant (Preview vs
// Original vs Thumbnail), resolution (single "W x H" field), file size,
// model used (Models), workflow used (Workflow).
function _viewerPersistence(opts) {
  var p = (opts && opts.persistence) || {};
  return {
    setFavorite: typeof p.setFavorite === "function" ? p.setFavorite : async function () {},
    setNote: typeof p.setNote === "function" ? p.setNote : async function () {},
    deleteGeneration: typeof p.deleteGeneration === "function" ? p.deleteGeneration : null,
    onChanged: typeof p.onChanged === "function" ? p.onChanged : null,
  };
}

// Canonical favorite star: one node carrying both the history and playground
// classes so either suite's selector matches the same button.
export function buildViewerFavoriteStar(record, persistence) {
  var rec = record || {};
  var persist = persistence || { setFavorite: async function () {}, onChanged: null };
  var star = el("button", {
    type: "button",
    class: "comfymodal-studio-viewer-favorite",
    "aria-label": rec.favorite ? "Remove from favorites" : "Add to favorites",
    "aria-pressed": rec.favorite ? "true" : "false",
    title: rec.favorite ? "Remove from favorites" : "Add to favorites",
    text: rec.favorite ? "\u2605" : "\u2606",
  });
  star.addEventListener("click", async function () {
    var next = !rec.favorite;
    star.disabled = true;
    try {
      await persist.setFavorite(rec, next);
      rec.favorite = next;
    } catch (err) { /* keep current state on failure */ }
    star.disabled = false;
    star.textContent = rec.favorite ? "\u2605" : "\u2606";
    star.setAttribute("aria-pressed", rec.favorite ? "true" : "false");
    star.setAttribute("aria-label", rec.favorite ? "Remove from favorites" : "Add to favorites");
    star.setAttribute("title", rec.favorite ? "Remove from favorites" : "Add to favorites");
    if (persist.onChanged) persist.onChanged();
  });
  return star;
}

// Delete button for the viewer's Run line: two-step inline confirm
// (Delete → Confirm delete + Cancel), no window.confirm. On success it
// notifies persistence.onChanged (feed refresh) and calls onClose (the
// shell's own close, which removes the overlay and runs surface cleanup).
// Rendered only when the persistence adapter offers deleteGeneration AND
// the record has an identity; otherwise returns null (no dead button).
export function buildViewerDeleteButton(record, persistence, onClose) {
  var rec = record || {};
  var persist = persistence || {};
  if (typeof persist.deleteGeneration !== "function") return null;
  if (rec.id == null || rec.id === "") return null;
  var wrap = el("span", { class: "comfymodal-studio-viewer-delete-wrap" });
  var delBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn comfymodal-studio-viewer-delete",
    "aria-label": "Delete this generation",
    title: "Delete this generation",
    "data-testid": "viewer-delete",
    text: "Delete",
  });
  var confirmBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn comfymodal-studio-viewer-delete-confirm",
    "aria-label": "Confirm delete",
    title: "Deletes the record, its attempts/assets, and owned files",
    "data-testid": "viewer-delete-confirm",
    text: "Confirm delete",
    hidden: true,
  });
  var cancelBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    "aria-label": "Cancel delete",
    "data-testid": "viewer-delete-cancel",
    text: "Cancel",
    hidden: true,
  });
  function setArmed(armed) {
    delBtn.hidden = armed;
    confirmBtn.hidden = !armed;
    cancelBtn.hidden = !armed;
  }
  delBtn.addEventListener("click", function () { setArmed(true); });
  cancelBtn.addEventListener("click", function () { setArmed(false); });
  confirmBtn.addEventListener("click", async function () {
    if (confirmBtn.disabled) return;
    confirmBtn.disabled = true;
    cancelBtn.disabled = true;
    confirmBtn.textContent = "Deleting\u2026";
    var failed = "";
    try {
      var result = await persist.deleteGeneration(rec);
      // Every repository flavor resolves a truthy-ok/accepted envelope on
      // success (v2 normalized, fixture accepted, bridge refused) — and the
      // v2 client never rejects, so a throw is a transport-level failure.
      if (result && (result.ok || result.accepted)) {
        if (typeof persist.onChanged === "function") persist.onChanged();
        if (typeof onClose === "function") onClose();
        return;
      }
      failed = result && result.message ? String(result.message) : "Delete was not accepted";
    } catch (err) {
      failed = err && err.message ? String(err.message) : "Delete failed";
    }
    confirmBtn.disabled = false;
    cancelBtn.disabled = false;
    confirmBtn.textContent = "Confirm delete";
    confirmBtn.title = failed;
    setArmed(false);
  });
  wrap.appendChild(delBtn);
  wrap.appendChild(confirmBtn);
  wrap.appendChild(cancelBtn);
  return wrap;
}

// Note editor for the viewer's Metadata accordion: Save/Cancel plus an
// Unsaved-changes affordance, with viewer-* testids. Deliberately NOT a
// nested card — a flat section sharing the card background, so it reads as
// part of Metadata instead of a box-in-a-box.
export function buildViewerNoteEditor(record, persistence) {
  var rec = record || {};
  var persist = persistence || { setNote: async function () {}, onChanged: null };
  var sec = el("div", {
    class: "comfymodal-studio-viewer-note-flat",
    "data-testid": "viewer-note-editor",
  }, [
    el("div", { class: "comfymodal-studio-viewer-card-title", text: "Note" }),
  ]);
  var textarea = el("textarea", {
    class: "comfymodal-studio-viewer-note comfymodal-input comfymodal-studio-textarea",
    "aria-label": "Note for this generation",
    "data-testid": "viewer-note-textarea",
  });
  textarea.value = rec.note || "";
  var savedNote = rec.note || "";
  var statusEl = el("span", {
    class: "comfymodal-studio-viewer-note-status",
    "data-testid": "viewer-note-status",
    role: "status",
  });
  var saveBtn = el("button", {
    class: "comfymodal-secondary-btn",
    type: "button",
    "data-testid": "viewer-note-save",
    text: "Save note",
  });
  var cancelBtn = el("button", {
    class: "comfymodal-secondary-btn",
    type: "button",
    "data-testid": "viewer-note-cancel",
    text: "Cancel",
  });
  function setStatus(text, color) {
    statusEl.textContent = text;
    statusEl.style.color = color || "";
  }
  textarea.addEventListener("input", function () {
    if (textarea.value !== savedNote) setStatus("Unsaved changes", "#fbbf24");
    else setStatus("", "");
  });
  saveBtn.addEventListener("click", async function () {
    if (textarea.value === savedNote) return;
    saveBtn.disabled = true;
    setStatus("Saving\u2026", "#888");
    try {
      await persist.setNote(rec, textarea.value);
      savedNote = textarea.value;
      rec.note = textarea.value;
      setStatus("Saved", "#4ade80");
    } catch (err) {
      setStatus("Save failed", "#f87171");
    }
    saveBtn.disabled = false;
    if (persist.onChanged) persist.onChanged();
  });
  cancelBtn.addEventListener("click", function () {
    textarea.value = savedNote;
    setStatus(savedNote ? "Note saved" : "", "#888");
  });
  sec.appendChild(textarea);
  sec.appendChild(el("div", { class: "comfymodal-studio-viewer-action-row" }, [saveBtn, cancelBtn, statusEl]));
  return sec;
}

// Lineage rows for the viewer's Metadata: where this image came from —
// generation/run identity, each attempt's mode + status, and whether the
// immutable request snapshot was saved. Flat rows (no sub-card). Returns an
// array (possibly empty); the caller filters/appends.
export function viewerSnapshotText(record) {
  var rec = record || {};
  if (rec.replayCapable == null) return "";
  if (rec.replayCapable) return "saved";
  var reason = viewerFirst(rec.replayReason, rec.replay_unavailable_reason);
  if (/missing_request_snapshot/.test(reason)) return "not saved for this run";
  return reason ? "unavailable (" + reason + ")" : "unavailable";
}
export function buildViewerAdvancedRows(record) {
  var rec = record || {};
  var pairs = [];
  var runId = rec.runId || rec.id;
  if (runId) pairs.push(["Run ID", runId]);
  if (rec.id && rec.id !== runId) pairs.push(["Generation", rec.id]);
  if (Array.isArray(rec.models) && rec.models.length) {
    pairs.push(["Models", rec.models.join(", ")]);
  }
  var attempts = Array.isArray(rec.attempts) ? rec.attempts : [];
  attempts.forEach(function (a, i) {
    var mode = (a && a.mode) || "run";
    var status = (a && a.status) || "";
    pairs.push([attempts.length > 1 ? "Attempt " + (i + 1) : "Attempt",
      status ? mode + " \u00b7 " + status : mode]);
  });
  var snap = viewerSnapshotText(rec);
  if (snap) pairs.push(["Request snapshot", snap]);
  return pairs
    .map(buildViewerMetaRow)
    .filter(function (row) { return row != null; });
}

// "Use parameters as base": fills the Playground shelf with this run's
// prompt + sampler controls (see viewerBasePayload). Rendered only when the
// caller supplies onUseAsBase AND the record yields a non-empty payload.
// The adapter returns the applied count; a positive count dismisses the
// overlay so the user lands on the filled shelf.
export function buildViewerUseAsBaseButton(record, onUseAsBase, onClose) {
  var payload = viewerBasePayload(record);
  if (typeof onUseAsBase !== "function") return null;
  if (!payload || Object.keys(payload).length === 0) return null;
  var btn = el("button", {
    class: "comfymodal-secondary-btn comfymodal-studio-viewer-use-base",
    type: "button",
    "data-testid": "viewer-use-as-base",
    text: "Use parameters as base",
    title: "Fill the Playground shelf with this run's prompt and controls",
  });
  btn.addEventListener("click", function () {
    if (btn.disabled) return;
    btn.disabled = true;
    var applied = 0;
    try { applied = Number(onUseAsBase(payload)) || 0; }
    catch (err) { applied = 0; }
    if (applied > 0) {
      if (typeof onClose === "function") onClose();
      return;
    }
    btn.textContent = "Nothing to apply";
    setTimeout(function () {
      btn.disabled = false;
      btn.textContent = "Use parameters as base";
    }, 1400);
  });
  return btn;
}

// One metadata spec row ([key, value] → element or null when blank).
export function buildViewerMetaRow(pair) {
  var text = viewerValueText(pair[1]);
  return text ? el("div", { class: "comfymodal-studio-viewer-row" }, [
    el("span", { class: "comfymodal-studio-viewer-row-key", text: pair[0] }),
    el("span", { class: "comfymodal-studio-viewer-row-value", text: text }),
  ]) : null;
}

// Clipboard write with a non-Clipboard-API fallback (older contexts).
function _copyTextToClipboard(text, done) {
  if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
    return;
  }
  try {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    var ok = document.execCommand("copy");
    if (ta.parentNode) ta.parentNode.removeChild(ta);
    done(!!ok);
  } catch (err) {
    done(false);
  }
}

// File row for the viewer's Metadata: stored filename plus native actions —
// Open file (OS default viewer), Open folder (file manager), Copy path.
// All three POST through the caller's `fileActions` adapter
// ({ openAsset(assetId), revealAsset(assetId) }) so only database-registered
// local files can ever be launched; remote/unknown assets show no buttons.
// Flat row, no card. Returns null when neither a filename nor a path known.
export function buildViewerFileRow(record, fileActions) {
  var rec = record || {};
  var outs = Array.isArray(rec.outputs) ? rec.outputs : [];
  var feat = rec.featuredOutput && typeof rec.featuredOutput === "object" ? rec.featuredOutput : {};
  function first(keys) {
    var list = Array.isArray(keys) ? keys : [keys];
    var sources = [feat].concat(outs);
    for (var i = 0; i < sources.length; i++) {
      var o = sources[i] || {};
      for (var j = 0; j < list.length; j++) {
        var v = o[list[j]];
        if (v != null && v !== "") return String(v);
      }
    }
    return "";
  }
  var filename = first("filename");
  var path = first("path");
  var assetId = first(["assetId", "asset_id"]);
  if (!filename && !path) return null;
  var actions = fileActions && typeof fileActions === "object" ? fileActions : {};
  var valueWrap = el("span", { class: "comfymodal-studio-viewer-row-value comfymodal-studio-viewer-file-value" });
  valueWrap.appendChild(el("span", {
    class: "comfymodal-studio-viewer-file-name",
    text: filename || path,
    title: path || filename,
  }));
  function actionButton(testid, label, title, send) {
    var btn = el("button", {
      class: "comfymodal-secondary-btn comfymodal-studio-viewer-file-btn",
      type: "button",
      "data-testid": testid,
      text: label,
      title: title,
    });
    btn.addEventListener("click", async function () {
      if (btn.disabled) return;
      btn.disabled = true;
      btn.textContent = label + "\u2026";
      var message = "";
      try {
        var result = await send();
        if (result && result.ok) {
          btn.textContent = label === "Copy path" ? "Copied" : "Opened";
        } else {
          btn.textContent = "Failed";
          message = result && result.message ? String(result.message) : "";
        }
      } catch (err) {
        btn.textContent = "Failed";
        message = err && err.message ? String(err.message) : "";
      }
      if (message) btn.title = message;
      setTimeout(function () {
        btn.disabled = false;
        btn.textContent = label;
      }, 1400);
    });
    return btn;
  }
  if (assetId && typeof actions.openAsset === "function") {
    valueWrap.appendChild(actionButton("viewer-file-open", "Open file",
      "Open in the system default viewer", function () { return actions.openAsset(assetId); }));
  }
  if (assetId && typeof actions.revealAsset === "function") {
    valueWrap.appendChild(actionButton("viewer-file-reveal", "Open folder",
      "Reveal in the file manager", function () { return actions.revealAsset(assetId); }));
  }
  if (path) {
    valueWrap.appendChild(actionButton("viewer-file-copy-path", "Copy path",
      "Copy the file path: " + path, function () {
        return new Promise(function (resolve) {
          _copyTextToClipboard(path, function (ok) {
            resolve({ ok: ok, message: ok ? "" : "clipboard unavailable" });
          });
        });
      }));
  }
  return el("div", { class: "comfymodal-studio-viewer-row" }, [
    el("span", { class: "comfymodal-studio-viewer-row-key", text: "File" }),
    valueWrap,
  ]);
}

export function buildSharedViewerOverlay(opts = {}) {
  var record = opts.record || {};
  var persistence = _viewerPersistence(opts);
  var params = viewerMergedParams(record);
  var prompt = viewerFirst(record.prompt, params.prompt);
  var negative = viewerFirst(record.negativePrompt, record.negative_prompt, params.negative_prompt, params.negativePrompt);

  var status = viewerValueText(record.status || "completed");
  var runLine = [el("span", { class: "comfymodal-studio-viewer-status", text: status })];
  if (record.startedAt) runLine.push(el("span", { class: "comfymodal-studio-viewer-muted", text: viewerDateText(record.startedAt) }));
  if (record.durationMs != null) runLine.push(el("span", { class: "comfymodal-studio-viewer-muted", text: viewerDurationText(record.durationMs) }));
  runLine.push(buildViewerFavoriteStar(record, persistence));
  var deleteBtn = buildViewerDeleteButton(record, persistence,
    typeof opts.onClose === "function" ? opts.onClose : null);
  if (deleteBtn) runLine.push(deleteBtn);

  var useAsBaseBtn = buildViewerUseAsBaseButton(record,
    typeof opts.onUseAsBase === "function" ? opts.onUseAsBase : null,
    typeof opts.onClose === "function" ? opts.onClose : null);
  var right = [
    buildViewerCard("Run", [el("div", { class: "comfymodal-studio-viewer-run-line" }, runLine)]),
    buildViewerCard("Run Data", [
      buildViewerPromptAccordion(prompt, negative),
      buildViewerParamsGrid(params, "preview-parameters", record),
      useAsBaseBtn,
    ]),
  ];
  // Core file facts. Completed is deliberately absent (Started + the Run
  // line's duration already pin the run in time); Workflow always renders
  // ("Not recorded" when no workflow/preset was captured).
  var metaRows = [
    ["Variant", viewerFirst(opts.variant, "")],
    ["Started", viewerDateText(record.startedAt)],
    ["Workflow", viewerFirst(record.workflow, record.preset) || "Not recorded"],
    ["Version", record.workflowVersion],
    ["Resolution", viewerResolutionText(params, record)],
    ["File size", viewerFileSizeText(opts.fileSize != null && opts.fileSize !== "" ? opts.fileSize : viewerFileSizeValue(record))],
    ["Format", viewerFirst(
      opts.format,
      record.featuredOutput && record.featuredOutput.format,
      Array.isArray(record.outputs) && record.outputs[0] ? record.outputs[0].format : ""
    )],
  ].map(buildViewerMetaRow).filter(function (row) { return row != null; });
  var fileRow = buildViewerFileRow(record, opts.fileActions);
  if (fileRow) metaRows.push(fileRow);
  if (Array.isArray(record.tags) && record.tags.length) {
    metaRows.push(buildViewerMetaRow(["Tags", record.tags.join(", ")]));
  }
  right.push(buildViewerAccordion("Metadata", metaRows));

  // Advanced: identity, provenance, replay state.
  var advancedRows = buildViewerAdvancedRows(record);
  if (advancedRows.length > 0) {
    right.push(buildViewerAccordion("Advanced", advancedRows));
  }

  right.push(buildViewerAccordion("Note", [buildViewerNoteEditor(record, persistence)]));

  // Truthful failure chrome: a failed full-quality render with a retained
  // preview gets the documented badge under the zoom stage on both surfaces.
  var stageBadges = [];
  if (record.fullRenderFailed) {
    stageBadges.push(el("div", {
      class: "comfymodal-studio-viewer-badge",
      "data-testid": "viewer-render-failed-badge",
      text: "Original failed \u2014 Data Saver retained",
    }));
  }

  return buildViewerBody({
    imageUrl: opts.imageUrl || "",
    rightChildren: right,
    stageBadges: stageBadges,
    timing: opts.timing || record.timing || record.timings || record.rawTiming || {},
  });
}

/**
 * Create a shared image preview overlay with zoomable image and
 * configurable info sections. Generic single-image viewing foundation
 * (currently without a production caller — see the region note above);
 * the Phase I5 A/B compare uses its own aligned two-image stage instead.
 *
 * Toolbar (close / save / download + zoom controls) renders BELOW the
 * image. Save comes before fullscreen in the row order.
 *
 * @param {object} opts
 * @param {string|null}  opts.imageUrl      - Image URL or null for no-image state
 * @param {string}       opts.alt           - Alt text for the image
 * @param {function}     opts.onClose       - Called when overlay should close
 * @param {function}     [opts.onKeyDown]   - Called for every keydown (after Escape/numpad checks), receives KeyboardEvent, return true to consume
 * @param {Array<HTMLElement>} [opts.sections] - DOM elements rendered below the image
 * @param {HTMLElement}  [opts.sideColumn]  - DOM element rendered as a right-side
 *   vertical column overlaying the image edge (does not shift the centered image)
 * @param {object}       [opts.saveOutput]  - { saved, onSave, errorMessage } —
 *   renders a Save button when provided; hidden when the record is already saved
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
  var stage = document.createElement("div");
  stage.className = "comfymodal-studio-preview-overlay-stage";

  // ── Toolbar buttons (rendered below the image in the zoom controls) ──
  var closeBtn = document.createElement("button");
  closeBtn.className = "comfymodal-studio-preview-overlay-close";
  closeBtn.setAttribute("aria-label", "Close preview");
  closeBtn.textContent = "\u00d7";
  closeBtn.style.cssText = "background:transparent;border:none;color:#ccc;font-size:18px;cursor:pointer;line-height:1;padding:2px 6px;position:static;top:auto;right:auto;z-index:auto;";
  closeBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    close();
  });

  var extraControls = [closeBtn];

  // Save-output button (single-output backend action).  Visibility is
  // driven by the caller via opts.saveOutput: the button is only rendered
  // for unsaved records.
  var saveError = null;
  if (opts.saveOutput) {
    var saveBtn = document.createElement("button");
    saveBtn.className = "comfymodal-studio-save-btn";
    saveBtn.setAttribute("data-testid", "save-output-btn");
    saveBtn.setAttribute("aria-label", "Save output");
    saveBtn.textContent = "Save";
    saveBtn.title = "Save output to the local outputs folder";
    saveBtn.style.cssText = "background:transparent;border:none;color:#ccc;font-size:11px;cursor:pointer;line-height:1;padding:2px 6px;";
    saveBtn.addEventListener("click", async function (e) {
      e.stopPropagation();
      if (saveBtn.disabled) return;
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving\u2026";
      if (saveError) saveError.style.display = "none";
      try {
        var ok = await opts.saveOutput.onSave();
        if (ok === false) throw new Error("save failed");
        saveBtn.style.display = "none";
      } catch (err) {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save";
        if (saveError) {
          saveError.textContent = (opts.saveOutput.errorMessage || "Save failed")
            + (err && err.message ? ": " + err.message : "");
          saveError.style.display = "block";
        }
      }
    });
    extraControls.push(saveBtn);
  }

  // Download button (only when image URL is present).  No transient
  // status text in the toolbar — failures surface via the button title.
  if (opts.imageUrl) {
    extraControls.push(_buildDownloadButton(opts));
  }

  // Zoomable image or no-image placeholder
  if (opts.imageUrl) {
    _zoomObj = createZoomableImageEl(opts.imageUrl, opts.alt, {
      extraControls: extraControls,
    });
    stage.appendChild(_zoomObj.container);
  } else {
    var noImg = document.createElement("div");
    noImg.className = "comfymodal-studio-preview-overlay-noimage";
    noImg.textContent = "No image available";
    stage.appendChild(noImg);
  }

  // Save error line (below the image, hidden until a failure occurs)
  if (opts.saveOutput) {
    saveError = document.createElement("div");
    saveError.className = "comfymodal-studio-save-error";
    saveError.style.cssText = "display:none;font-size:11px;color:var(--color-danger, #f87171);max-width:100%;";
    saveError.setAttribute("data-testid", "save-output-error");
    stage.appendChild(saveError);
  }

  var details = opts.sideColumn || null;
  if (opts.sideColumn) {
    details.classList.add("comfymodal-studio-preview-overlay-side");
  }

  if (opts.sections && opts.sections.length > 0) {
    if (!details) {
      details = document.createElement("div");
      details.className = "comfymodal-studio-preview-overlay-side";
    }
    var sectionsWrap = document.createElement("div");
    sectionsWrap.className = "comfymodal-studio-preview-overlay-sections";
    for (var si = 0; si < opts.sections.length; si++) {
      sectionsWrap.appendChild(opts.sections[si]);
    }
    details.appendChild(sectionsWrap);
  }

  content.appendChild(stage);
  if (details) content.appendChild(details);

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

  function close(notify = true) {
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
    if (notify && typeof opts.onClose === "function") {
      opts.onClose();
    }
  }

  return { overlay: overlay, close: close, contentEl: content };
}

/**
 * Build the download button for the preview toolbar.  Failures are
 * surfaced via the button title/aria-label (no transient status text).
 */
function _buildDownloadButton(opts) {
  var dlBtn = document.createElement("button");
  dlBtn.className = "comfymodal-studio-download-btn";
  dlBtn.setAttribute("aria-label", "Download image");
  dlBtn.textContent = "\u2b07";
  dlBtn.title = "Download image";
  dlBtn.style.cssText = "background:transparent;border:none;color:#ccc;font-size:15px;cursor:pointer;line-height:1;padding:2px 6px;";

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
      dlBtn.title = "Download failed \u2014 try again";
      dlBtn.setAttribute("aria-label", "Download failed, try again");
    } finally {
      dlBtn.disabled = false;
      dlBtn.textContent = "\u2b07";
    }
  });

  return dlBtn;
}

// ── Generic empty-state primitive ────────────────────────────────────────
//
// Phase I3 shared primitive.  The previous renderer here was an ad-hoc
// backend-specific card with baked-in legacy copy ("No backends configured
// via legacy discovery.") and a destructive 4-argument signature that
// cleared two caller-owned containers.  It had zero runtime callers (only a
// never-invoked re-export wrapper in studio-backend.js), so it is replaced
// by this generic, copy-free primitive.
//
// DELIBERATELY STAGED: page empty states (workflows/models/history/backend/
// playground) migrate onto this helper in I4/I6/I7/I8.  Having no production
// caller immediately after I3 is by design — this is planned downstream
// consumption, not accidental dead code.
//
// Contract:
//   renderEmptyState({ title, detail = "", action = null, testid } = {})
//   - root: class "cm-empty-state", optional data-testid
//   - title/detail rendered only when non-blank strings are supplied
//     (all user-facing copy comes from callers — none is baked in)
//   - action: an existing HTMLElement/Node appended WITHOUT cloning into
//     a "cm-empty-state-action" wrapper
//   - NO heading level is assigned (the page owner owns document hierarchy)
//   - NO role="alert" / aria-live: an empty state is normal application
//     state, not an automatic announcement

export function renderEmptyState(options = {}) {
  const opts = options && typeof options === "object" ? options : {};
  const root = el("div", { class: "cm-empty-state" });
  if (typeof opts.testid === "string" && opts.testid !== "") {
    root.setAttribute("data-testid", opts.testid);
  }
  const title = typeof opts.title === "string" ? opts.title.trim() : "";
  if (title !== "") {
    root.appendChild(el("div", { class: "cm-empty-state-title", text: title }));
  }
  const detail = typeof opts.detail === "string" ? opts.detail : "";
  if (detail.trim() !== "") {
    root.appendChild(el("div", { class: "cm-empty-state-detail", text: detail }));
  }
  if (opts.action && typeof opts.action.appendChild === "function") {
    const actionWrap = el("div", { class: "cm-empty-state-action" });
    actionWrap.appendChild(opts.action);
    root.appendChild(actionWrap);
  }
  return root;
}
