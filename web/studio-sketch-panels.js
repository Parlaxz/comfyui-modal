"use strict";
/**
 * studio-sketch-panels.js — Sketch tool/color/settings sidebar panels (Phase 6).
 *
 * Renders inside the ~333px LEFT Studio sidebar rail (mounted there by another
 * lane). Compact stacked rail DOM only: no floating/draggable panels, no new
 * global state architecture, no fixed widths over 300px, no giant canvases in
 * the default view.
 *
 * Compact rail organization (not a moved tall inspector):
 *   TOOLS   — 4-column grid x 2 rows (8 tools), Lucide icons, selected state.
 *   BRUSH   — Size/Opacity/Hardness sliders only, tight rows; Hardness
 *             disabled (not hidden) where N/A so layout stays stable.
 *   COLOR   — SHORT by default: FG/BG swatches + swap/reset, picker + hex,
 *             one compact preset row, fill tolerance. Full HSV wheel + SV +
 *             HSL/RGB rows live behind a collapsed-by-default "Advanced Color"
 *             disclosure.
 *   CANVAS  — one mini-row: zoom out/label/in + Fit + 100%.
 *   HISTORY — compact backup undo/redo row (testids kept); the sticky action
 *             bar lives in the playground shelf footer (other lane), so a
 *             one-line helper labels these as backup to avoid confusion.
 *
 * This module OWNS the tool bar, brush settings, color swatches and canvas
 * zoom/undo controls, and DRIVES the sketch engine exclusively through its
 * exact public setters. Clear/Save stay owned by the shell and are NOT
 * implemented here.
 *
 * Exact known-engine contract (single-name calls with typeof guards; no
 * setter-name guessing, no percent/fraction guessing):
 *   engine.setTool(name)
 *   engine.setSize(px)            // engine state key: brushSize (1..100)
 *   engine.setOpacity(1..100)     // percent scale, NOT 0..1
 *   engine.setHardness(1..100)    // percent scale, NOT 0..1
 *   engine.setColor(css)          // primary slot  (engine state: color)
 *   engine.setBgColor(css)        // secondary slot (engine state: bgColor;
 *                                 // the composite backdrop is separate and
 *                                 // is never driven from these panels)
 *   engine.setFillTolerance(n) or engine.setTolerance(n)
 *   engine.undo() / engine.redo()
 *   engine.zoomIn() / engine.zoomOut() / engine.fit() / engine.setZoom(1)
 *   engine.getState() -> { tool, brushSize, opacity, hardness, color,
 *     bgColor, zoom, canUndo, canRedo }
 *   engine.onChange(cb) -> unsubscribe fn (optional)
 *
 * Usage:
 *   var handle = ComfyModalSketchPanels.mountSketchPanels(container, engine, opts);
 *   handle.syncFromEngine();
 *   handle.destroy();
 */

(function (global) {
  // Lucide icons (ISC license): https://lucide.dev/license
  var ICONS = {
    brush: '<path d="m9.06 11.9 8.07-8.06a2.85 2.85 0 1 1 4.03 4.03l-8.06 8.08"/><path d="M7.07 14.94c-1.66 0-3 1.35-3 3.02 0 1.33-2.5 1.52-2 2.02 1.08 1.1 2.49 2.02 4 2.02 2.2 0 4-1.8 4-4.04a3.01 3.01 0 0 0-3-3.02z"/>',
    pencil: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>',
    eraser: '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>',
    line: '<path d="M5 19 19 5"/>', circle: '<circle cx="12" cy="12" r="9"/>',
    fill: '<path d="m19 11-8-8-8.6 8.6a2 2 0 0 0 0 2.8l5.2 5.2c.8.8 2 .8 2.8 0L19 11Z"/><path d="m5 2 5 5"/><path d="M2 13h15"/>',
    eyedropper: '<path d="m2 22 1-1h3l9-9"/><path d="M3 21v-3l9-9"/><path d="m15 6 3.4-3.4a2.1 2.1 0 1 1 3 3L18 9l.4.4a2.1 2.1 0 1 1-3 3l-3.8-3.8a2.1 2.1 0 1 1 3-3l.4.4Z"/>',
    rectangle: '<rect x="4" y="4" width="16" height="16" rx="1"/>',
    swap: '<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/>',
    reset: '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v8h8"/>', zoomIn: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4M11 8v6M8 11h6"/>', zoomOut: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4M8 11h6"/>',
    fit: '<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/>', undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>', redo: '<path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3l3 2.7"/>',
  };
  var TOOL_DEFS = [
    { id: "brush", label: "Brush", icon: "brush", key: "B" }, { id: "pencil", label: "Pencil", icon: "pencil", key: "P" },
    { id: "eraser", label: "Eraser", icon: "eraser", key: "E" }, { id: "line", label: "Line", icon: "line", key: "L" },
    { id: "rectangle", label: "Rectangle", icon: "rectangle", key: "R" }, { id: "circle", label: "Circle", icon: "circle", key: "C" },
    { id: "fill", label: "Fill", icon: "fill", key: "G" }, { id: "eyedropper", label: "Eyedropper", icon: "eyedropper", key: "I" },
  ];

  var DEFAULT_FG = "#000000";
  var DEFAULT_BG = "#ffffff";

  // Hardness applies to soft round tips only; other tools keep the slider
  // visible but disabled so the sidebar layout stays stable.
  var HARDNESS_TOOLS = { brush: true, pencil: true };

  function clampNum(v, lo, hi, fb) {
    var n = Number(v);
    if (!isFinite(n)) return fb;
    if (n < lo) return lo;
    if (n > hi) return hi;
    return n;
  }

  function normHex(v, fb) {
    var s = String(v == null ? "" : v).trim();
    if (!s) return fb;
    if (s[0] !== "#") s = "#" + s;
    // Accept #rgb / #rrggbb (ignore alpha); fall back otherwise.
    if (/^#[0-9a-fA-F]{6}$/.test(s)) return "#" + s.slice(1).toLowerCase();
    if (/^#[0-9a-fA-F]{3}$/.test(s)) {
      return ("#" + s[1] + s[1] + s[2] + s[2] + s[3] + s[3]).toLowerCase();
    }
    return fb;
  }

  function icon(name, label) {
    return '<svg class="sketch-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (ICONS[name] || "") + '</svg>' + (label || "");
  }

  function installStyles(doc) {
    if (!doc || doc.getElementById("sketch-panels-style")) return;
    var style = doc.createElement("style"); style.id = "sketch-panels-style";
    // Native dark Studio sidebar treatment, sized for the ~333px LEFT rail.
    // Tokens mirror web/studio-styles.js: panel #111 on sidebar #0d0d0d, 1px
    // #2a2a2a borders, 12px type, 11px uppercase section headers in #888,
    // muted helper #888, secondary buttons (#1a1a1a / #333 / #aaa), accent
    // var(--color-accent, #5a7fdb) for selected states, accent-color sliders.
    // Docked rail only — no position:fixed/absolute, no floats, no fixed
    // widths over 300px, max-width:100% everywhere so nothing overflows the
    // narrow sidebar. Wheel/SV canvases render small AND live inside the
    // collapsed Advanced disclosure, so the default view stays short.
    style.textContent = [
      ".sketch-panels{color:#d0d0d0;font:12px/1.45 system-ui,-apple-system,sans-serif;background:transparent;display:flex;flex-direction:column;gap:4px;padding:0;box-sizing:border-box;width:100%;max-width:100%;}",
      ".sketch-panels-section{background:#111;border:1px solid #2a2a2a;border-radius:4px;padding:8px;margin-bottom:4px;box-sizing:border-box;width:100%;max-width:100%;}",
      ".sketch-panels-heading{font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.05em;margin:0 0 6px;padding:0;}",
      ".sketch-panels-tools{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;max-width:100%;}",
      ".sketch-panels-tool,.sketch-panels-btn,.sketch-panels-mini{background:#1a1a1a;color:#aaa;border:1px solid #333;border-radius:6px;min-height:28px;cursor:pointer;font:inherit;font-size:11px;display:inline-flex;align-items:center;justify-content:center;gap:4px;padding:4px 6px;transition:background .15s,color .15s,border-color .15s;box-sizing:border-box;max-width:100%;}",
      ".sketch-panels-tool{flex-direction:column;font-size:9px;padding:5px 2px;min-height:38px;}",
      ".sketch-panels-tool:hover,.sketch-panels-btn:hover,.sketch-panels-mini:hover{background:#222;color:#d0d0d0;}",
      ".sketch-panels-tool:focus-visible,.sketch-panels-btn:focus-visible,.sketch-panels-mini:focus-visible{outline:2px solid var(--color-accent,#5a7fdb);outline-offset:1px;}",
      ".sketch-panels-tool.is-active{background:var(--color-accent-muted,rgba(90,127,219,.16));border-color:var(--color-accent,#5a7fdb);color:#fff;}",
      ".sketch-panels-tool:disabled,.sketch-panels-btn:disabled,.sketch-panels-mini:disabled{opacity:.45;cursor:default;}",
      ".sketch-icon{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex-shrink:0;}",
      ".sketch-panels-tool.is-active .sketch-icon{stroke:#fff;}",
      ".sketch-panels-row{display:flex;align-items:center;gap:8px;margin:6px 0;max-width:100%;}",
      ".sketch-panels-row:last-child{margin-bottom:0;}",
      ".sketch-panels-label{display:flex;align-items:center;gap:6px;width:100%;color:#a0a0a0;font-size:11px;font-weight:500;}",
      ".sketch-panels-slider,.comfysketch-slider{flex:1;min-width:0;accent-color:var(--color-accent,#5a7fdb);height:16px;background:transparent;cursor:pointer;}",
      ".sketch-panels-slider:disabled,.comfysketch-slider:disabled{opacity:.4;cursor:default;}",
      ".sketch-panels-val{min-width:38px;text-align:right;color:#888;font-size:11px;font-variant-numeric:tabular-nums;}",
      ".sketch-panels-swatches{display:flex;align-items:center;gap:4px;margin:6px 0;max-width:100%;}",
      ".sketch-panels-swatch{width:30px;height:24px;border-radius:4px;border:1px solid #333;cursor:pointer;padding:0;font-size:0;flex-shrink:0;box-sizing:border-box;}",
      ".sketch-panels-swatch.is-active{outline:2px solid var(--color-accent,#5a7fdb);outline-offset:1px;}",
      ".sketch-panels-swatch:focus-visible{outline:2px solid var(--color-accent,#5a7fdb);outline-offset:1px;}",
      ".sketch-panels-mini{min-width:26px;}",
      ".sketch-panels-colorbox{display:flex;gap:8px;align-items:flex-start;justify-content:flex-start;margin:4px 0;max-width:100%;}",
      ".sketch-panels-colorbox canvas{width:84px;height:84px;border:1px solid #333;border-radius:4px;background:#0a0a0a;cursor:crosshair;touch-action:none;}",
      ".sketch-panels-color{width:28px;height:24px;padding:0;border:1px solid #333;border-radius:4px;background:#0a0a0a;cursor:pointer;flex-shrink:0;}",
      ".sketch-panels-hex{flex:1;min-width:0;background:#0a0a0a;border:1px solid #2a2a2a;color:#d0d0d0;border-radius:3px;padding:4px 6px;font-size:11px;font-family:ui-monospace,monospace;box-sizing:border-box;}",
      ".sketch-panels-hex:focus{border-color:var(--color-accent,#5a7fdb);outline:none;}",
      ".sketch-panels-presets{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:3px;margin:6px 0 0;max-width:100%;}",
      ".sketch-panels-preset{aspect-ratio:1;border:1px solid #333;border-radius:3px;cursor:pointer;padding:0;min-width:0;}",
      ".sketch-panels-preset:hover{border-color:var(--color-accent,#5a7fdb);}",
      ".sketch-panels-preset:focus-visible{outline:2px solid var(--color-accent,#5a7fdb);outline-offset:1px;}",
      ".sketch-panels-number{width:52px;background:#0a0a0a;border:1px solid #2a2a2a;color:#d0d0d0;border-radius:3px;padding:3px 6px;font-size:11px;box-sizing:border-box;}",
      ".sketch-panels-number:focus{border-color:var(--color-accent,#5a7fdb);outline:none;}",
      ".sketch-panels-zoomrow{display:flex;align-items:center;gap:4px;max-width:100%;}",
      ".sketch-panels-zoomlabel{flex:1;text-align:center;color:#888;font-size:11px;font-variant-numeric:tabular-nums;min-width:40px;}",
      ".sketch-panels-histrow{display:flex;gap:4px;margin-top:4px;max-width:100%;}",
      ".sketch-panels-histrow .sketch-panels-btn{flex:1;}",
      ".sketch-panels-help{font-size:11px;color:#888;margin:2px 0 0;line-height:1.4;}",
      ".sketch-panels-advanced-toggle{display:flex;align-items:center;gap:4px;width:100%;margin-top:6px;padding:5px 8px;background:#0a0a0a;border:1px solid #2a2a2a;border-radius:3px;cursor:pointer;font:inherit;font-size:10px;font-weight:600;color:#a0a0a0;text-transform:uppercase;letter-spacing:.04em;text-align:left;box-sizing:border-box;}",
      ".sketch-panels-advanced-toggle:hover{background:#1a1a1a;color:#d0d0d0;}",
      ".sketch-panels-advanced-toggle:focus-visible{outline:2px solid var(--color-accent,#5a7fdb);outline-offset:1px;}",
      ".sketch-panels-advanced-toggle .arrow{font-size:8px;flex-shrink:0;transition:transform .2s;}",
      '.sketch-panels-advanced-toggle[aria-expanded="true"] .arrow{transform:rotate(90deg);}',
      ".sketch-panels-advanced-body{display:flex;flex-direction:column;gap:4px;padding:6px 0 0 8px;margin:4px 0 0 4px;border-left:1px solid #2a2a2a;max-width:100%;}",
      '.sketch-panels-advanced-body[hidden]{display:none;}',
      ".sketch-panels-rgbrow{display:flex;align-items:center;gap:4px;max-width:100%;}",
      ".sketch-panels-rgbrow .sketch-panels-number{width:44px;}",
      ".sketch-panels-rgbrow .sketch-panels-val{min-width:12px;}",
    ].join("");
    (doc.head || doc.documentElement).appendChild(style);
  }

  /** Best-effort snapshot of the exact known-engine state; never throws. */
  function readState(eng) {
    var raw = {};
    if (eng && typeof eng.getState === "function") {
      try {
        var g = eng.getState();
        if (g && typeof g === "object") raw = g;
      } catch (_e) {
        raw = {};
      }
    }
    // Exact keys only — no alias lists. Panel maps brushSize->size,
    // color->fg, bgColor->bg. Tolerance is write-only (see setFillTolerance);
    // sync keeps the panel-local value.
    return {
      tool: raw.tool,
      size: raw.brushSize,
      opacity: raw.opacity,
      hardness: raw.hardness,
      fg: raw.color,
      bg: raw.bgColor,
      tolerance: undefined,
      zoom: raw.zoom,
      canUndo: raw.canUndo,
      canRedo: raw.canRedo,
    };
  }

  // Exact engine scale is percent 1..100 (NOT 0..1), so slider and engine
  // share one scale with no value-dependent branching. In particular an
  // engine value of 1 means 1%, never a 1.0 fraction.
  function opacityToSlider(op) {
    var n = Number(op);
    if (!isFinite(n)) return 100;
    return Math.round(clampNum(n, 0, 100, 100));
  }

  function sliderToOpacity(slider) {
    return Math.round(clampNum(slider, 0, 100, 100));
  }

  function hardnessToSlider(h) {
    var n = Number(h);
    if (!isFinite(n)) return 100;
    return Math.round(clampNum(n, 0, 100, 100));
  }

  function sliderToHardness(slider) {
    return Math.round(clampNum(slider, 0, 100, 100));
  }

  /**
   * mountSketchPanels(container, engine, opts) -> { destroy(), syncFromEngine() }
   * opts: { keyboard=true } — keyboard shortcuts attach to the container's
   * owner document and ignore keystrokes inside editable fields.
   */
  function mountSketchPanels(container, engine, opts) {
    var eng = engine || {};
    var options = opts || {};
    var keyboard = options.keyboard !== false;

    function noopHandle() {
      return {
        destroy: function () {},
        syncFromEngine: function () {},
      };
    }

    if (!container || typeof document === "undefined") return noopHandle();

    var doc = (container.ownerDocument || document);
    var docAtMount = doc;
    var mounted = true;
    installStyles(doc);
    var state = {
      tool: "brush",
      size: 12,
      opacity: 100, // slider scale 0..100 == engine percent scale
      hardness: 100, // slider scale 0..100 == engine percent scale
      fg: DEFAULT_FG,
      bg: DEFAULT_BG,
      slot: "fg", // which swatch the color picker edits
      tolerance: 32,
      zoom: null,
    };

    var toolBtns = {};
    var undoBtn = null;
    var redoBtn = null;
    var zoomLabel = null;
    var sizeSlider = null;
    var sizeVal = null;
    var opacitySlider = null;
    var opacityVal = null;
    var hardnessSlider = null;
    var hardnessVal = null;
    var colorPicker = null;
    var hexInput = null;
    var fgSwatch = null;
    var bgSwatch = null;
    var tolInput = null;
    var wheelCanvas = null;
    var svCanvas = null;
    var advToggle = null;
    var advBody = null;
    var rgbInputs = null;
    var hslInputs = null;
    var hue = 0;
    var sat = 0;
    var val = 0;
    var unsubscribe = null;

    var root = doc.createElement("div");
    root.className = "sketch-panels sketch-panels--dark";
    root.setAttribute("data-sketch-panels", "1");

    function el(tag, cls, text) {
      var n = doc.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined && text !== null) n.textContent = text;
      return n;
    }

    function section(title) {
      // Keep legacy section/heading classes; ADD the Studio control-group
      // class so the sidebar cascade treats these as native sections.
      var s = el("div", "sketch-panels-section comfymodal-studio-control-group");
      var h = el("div", "sketch-panels-heading", title);
      s.appendChild(h);
      root.appendChild(s);
      return s;
    }

    function paintToolButtons() {
      for (var i = 0; i < TOOL_DEFS.length; i++) {
        (function (def) {
          var b = toolBtns[def.id];
          if (!b) return;
          var on = state.tool === def.id;
          if (on) b.classList.add("is-active");
          else b.classList.remove("is-active");
          b.setAttribute("aria-pressed", on ? "true" : "false");
        })(TOOL_DEFS[i]);
      }
    }

    function paintSwatches() {
      if (fgSwatch) {
        fgSwatch.style.background = state.fg;
        fgSwatch.classList.toggle("is-active", state.slot === "fg");
        fgSwatch.setAttribute("aria-pressed", state.slot === "fg" ? "true" : "false");
      }
      if (bgSwatch) {
        bgSwatch.style.background = state.bg;
        bgSwatch.classList.toggle("is-active", state.slot === "bg");
        bgSwatch.setAttribute("aria-pressed", state.slot === "bg" ? "true" : "false");
      }
      var activeColor = state.slot === "bg" ? state.bg : state.fg;
      if (colorPicker) colorPicker.value = normHex(activeColor, DEFAULT_FG);
      if (hexInput && doc.activeElement !== hexInput) hexInput.value = normHex(activeColor, DEFAULT_FG);
      paintAdvInputs(activeColor);
    }

    function hexToRgb(hex) {
      var h = normHex(hex, "#000000").slice(1);
      return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16) };
    }
    function rgbToHex(r, g, b) {
      function q(n) { return clampNum(Math.round(Number(n)), 0, 255, 0).toString(16).padStart(2, "0"); }
      return ("#" + q(r) + q(g) + q(b)).toLowerCase();
    }
    function rgbToHsv(rgb) {
      var r = rgb.r / 255, g = rgb.g / 255, b = rgb.b / 255, max = Math.max(r,g,b), min = Math.min(r,g,b), d = max-min, h = 0;
      if (d) { h = max === r ? ((g-b)/d)%6 : max === g ? (b-r)/d+2 : (r-g)/d+4; h *= 60; if (h < 0) h += 360; }
      return { h:h, s:max ? d/max : 0, v:max };
    }
    function hsvToHex(h, s, v) {
      var c=v*s, x=c*(1-Math.abs((h/60)%2-1)), m=v-c, r=0,g=0,b=0;
      if(h<60){r=c;g=x;} else if(h<120){r=x;g=c;} else if(h<180){g=c;b=x;} else if(h<240){g=x;b=c;} else if(h<300){r=x;b=c;} else {r=c;b=x;}
      function q(n){return Math.round((n+m)*255).toString(16).padStart(2,"0");}
      return "#"+q(r)+q(g)+q(b);
    }
    function rgbToHsl(rgb) {
      var r = rgb.r / 255, g = rgb.g / 255, b = rgb.b / 255;
      var max = Math.max(r, g, b), min = Math.min(r, g, b), h = 0, s = 0, l = (max + min) / 2;
      var d = max - min;
      if (d) {
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        if (max === r) h = ((g - b) / d) % 6;
        else if (max === g) h = (b - r) / d + 2;
        else h = (r - g) / d + 4;
        h *= 60;
        if (h < 0) h += 360;
      }
      return { h: h, s: s * 100, l: l * 100 };
    }
    function hslToHex(h, s, l) {
      h = ((Number(h) % 360) + 360) % 360;
      s = clampNum(Number(s), 0, 100, 0) / 100;
      l = clampNum(Number(l), 0, 100, 0) / 100;
      var c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = l - c / 2;
      var r = 0, g = 0, b = 0;
      if (h < 60) { r = c; g = x; } else if (h < 120) { r = x; g = c; } else if (h < 180) { g = c; b = x; }
      else if (h < 240) { g = x; b = c; } else if (h < 300) { r = x; b = c; } else { r = c; b = x; }
      function q(n) { return Math.round((n + m) * 255).toString(16).padStart(2, "0"); }
      return ("#" + q(r) + q(g) + q(b)).toLowerCase();
    }
    function paintAdvInputs(activeColor) {
      var hex = normHex(activeColor, null);
      if (!hex) return;
      var rgb = hexToRgb(hex);
      var hsl = rgbToHsl(rgb);
      if (rgbInputs) {
        if (doc.activeElement !== rgbInputs.r) rgbInputs.r.value = String(rgb.r);
        if (doc.activeElement !== rgbInputs.g) rgbInputs.g.value = String(rgb.g);
        if (doc.activeElement !== rgbInputs.b) rgbInputs.b.value = String(rgb.b);
      }
      if (hslInputs) {
        if (doc.activeElement !== hslInputs.h) hslInputs.h.value = String(Math.round(hsl.h));
        if (doc.activeElement !== hslInputs.s) hslInputs.s.value = String(Math.round(hsl.s));
        if (doc.activeElement !== hslInputs.l) hslInputs.l.value = String(Math.round(hsl.l));
      }
    }
    function drawColorCanvases() {
      if (!wheelCanvas || !svCanvas) return;
      try {
        var size=128, ctx=wheelCanvas.getContext("2d"), sctx=svCanvas.getContext("2d"), cx=64, cy=64;
        if (!ctx || !sctx) return;
        ctx.clearRect(0,0,size,size); for(var a=0;a<360;a++){var g=ctx.createLinearGradient(0,0,128,0);g.addColorStop(0,"hsl("+a+",100%,50%)");g.addColorStop(1,"hsl("+(a+1)+",100%,50%)");ctx.strokeStyle=g;ctx.lineWidth=12;ctx.beginPath();ctx.arc(cx,cy,51,(a-1)*Math.PI/180,a*Math.PI/180);ctx.stroke();}
        // SAME angle convention as the segments above: hue a is drawn at canvas
        // angle a (0 = east, increasing clockwise as canvas y grows downward).
        ctx.strokeStyle="#fff";ctx.lineWidth=2;ctx.beginPath();ctx.arc(cx,cy,51,(hue-1)*Math.PI/180,hue*Math.PI/180);ctx.stroke();
        sctx.clearRect(0,0,size,size); var grad=sctx.createLinearGradient(20,0,108,0);grad.addColorStop(0,"#fff");grad.addColorStop(1,"hsl("+hue+",100%,50%)");sctx.fillStyle=grad;sctx.fillRect(22,22,84,84);var black=sctx.createLinearGradient(0,22,0,106);black.addColorStop(0,"transparent");black.addColorStop(1,"#000");sctx.fillStyle=black;sctx.fillRect(22,22,84,84);sctx.strokeStyle="#fff";sctx.lineWidth=2;sctx.beginPath();sctx.arc(22+sat*84,106-val*84,4,0,Math.PI*2);sctx.stroke();
      } catch (_e) { /* canvas is best-effort (e.g. headless tests) */ }
    }
    function setColorFromHsv() { driveColor(hsvToHex(hue,sat,val), state.slot); drawColorCanvases(); }
    function colorPoint(ev, canvas) {
      var r=canvas.getBoundingClientRect();
      var w=(r.width && r.width > 0) ? r.width : 128;
      var h=(r.height && r.height > 0) ? r.height : 128;
      return { x:(ev.clientX-r.left)/w*128-64, y:(ev.clientY-r.top)/h*128-64 };
    }
    function hueFromPoint(p) {
      // SAME convention as drawWheel: hue a lives at canvas angle a.
      return ((Math.atan2(p.y,p.x)*180/Math.PI)+360)%360;
    }
    function handleColorPoint(ev, canvas) {
      var p=colorPoint(ev,canvas);
      // Ring-vs-square (upstream ComfySketch): the inner 84x84 square
      // (canvas 22..106, i.e. dx,dy in [-42,42]) edits SV; anything outside
      // it edits hue by angle. One shared handler is bound to BOTH stacked
      // canvases, so ring clicks landing on the transparent part of the top
      // SV canvas still resolve to hue instead of being swallowed as SV.
      if(p.x>=-42&&p.x<=42&&p.y>=-42&&p.y<=42){sat=clampNum((p.x+42)/84,0,1,0);val=clampNum(1-(p.y+42)/84,0,1,1);}else{hue=hueFromPoint(p);}
      setColorFromHsv();
    }
    function bindColorCanvas(canvas) { canvas.addEventListener("pointerdown",function(ev){ if(ev.preventDefault) ev.preventDefault(); try { if(canvas.setPointerCapture && ev.pointerId !== undefined) canvas.setPointerCapture(ev.pointerId); } catch(_e){} function move(e){handleColorPoint(e,canvas);} function up(){canvas.removeEventListener("pointermove",move);canvas.removeEventListener("pointerup",up);canvas.removeEventListener("pointercancel",up);} move(ev); canvas.addEventListener("pointermove",move); canvas.addEventListener("pointerup",up); canvas.addEventListener("pointercancel",up);}); }

    function paintZoom() {
      if (!zoomLabel) return;
      if (state.zoom == null || !isFinite(Number(state.zoom))) {
        zoomLabel.textContent = "";
        return;
      }
      // Exact engine zoom is a scale factor (1 = 100%); no percent guessing.
      zoomLabel.textContent = String(Math.round(Number(state.zoom) * 100)) + "%";
    }

    function paintUndoRedo() {
      var s = readState(eng);
      if (undoBtn) {
        var cu = s.canUndo;
        undoBtn.disabled = cu === false || (typeof eng.canUndo === "function" && safeCan(eng.canUndo, eng) === false);
      }
      if (redoBtn) {
        var cr = s.canRedo;
        redoBtn.disabled = cr === false || (typeof eng.canRedo === "function" && safeCan(eng.canRedo, eng) === false);
      }
    }

    function safeCan(fn, ctx) {
      try {
        return fn.call(ctx);
      } catch (_e) {
        return undefined;
      }
    }

    // ---- engine drivers (exact public setters only) ----

    function driveTool(id) {
      state.tool = id;
      if (typeof eng.setTool === "function") {
        try { eng.setTool(id); } catch (_e) { /* engine setter failure is non-fatal */ }
      }
      paintToolButtons();
      syncHardnessEnabled();
    }

    function driveSize(px) {
      state.size = clampNum(px, 1, 200, 12);
      if (typeof eng.setSize === "function") {
        try { eng.setSize(state.size); } catch (_e) { /* non-fatal */ }
      }
      if (sizeSlider && sizeSlider.value !== String(state.size)) sizeSlider.value = String(state.size);
      if (sizeVal) sizeVal.textContent = String(state.size) + "px";
    }

    function driveOpacity(slider) {
      state.opacity = Math.round(clampNum(slider, 0, 100, 100));
      if (typeof eng.setOpacity === "function") {
        try { eng.setOpacity(sliderToOpacity(state.opacity)); } catch (_e) { /* non-fatal */ }
      }
      if (opacitySlider && opacitySlider.value !== String(state.opacity)) opacitySlider.value = String(state.opacity);
      if (opacityVal) opacityVal.textContent = String(state.opacity) + "%";
    }

    function driveHardness(slider) {
      state.hardness = Math.round(clampNum(slider, 0, 100, 100));
      if (typeof eng.setHardness === "function") {
        try { eng.setHardness(sliderToHardness(state.hardness)); } catch (_e) { /* non-fatal */ }
      }
      if (hardnessSlider && hardnessSlider.value !== String(state.hardness)) hardnessSlider.value = String(state.hardness);
      if (hardnessVal) hardnessVal.textContent = String(state.hardness) + "%";
    }

    function driveColor(css, slot) {
      var hex = normHex(css, null);
      if (!hex) return;
      var target = slot || state.slot || "fg";
      if (target === "bg") {
        state.bg = hex;
        // Secondary swatch only. The composite backdrop setter is separate
        // and must never be driven here; without the exact slot setter the
        // color stays panel-local so swap still works.
        if (typeof eng.setBgColor === "function") {
          try { eng.setBgColor(hex); } catch (_e) { /* non-fatal */ }
        }
      } else {
        state.fg = hex;
        if (typeof eng.setColor === "function") {
          try { eng.setColor(hex); } catch (_e) { /* non-fatal */ }
        }
      }
      var hsv = rgbToHsv(hexToRgb(hex)); hue = hsv.h; sat = hsv.s; val = hsv.v;
      paintSwatches();
    }

    function swapFgBg() {
      var t = state.fg;
      state.fg = state.bg;
      state.bg = t;
      // Push both slots through the exact setters (secondary via setBgColor).
      if (typeof eng.setColor === "function") {
        try { eng.setColor(state.fg); } catch (_e) { /* non-fatal */ }
      }
      if (typeof eng.setBgColor === "function") {
        try { eng.setBgColor(state.bg); } catch (_e) { /* non-fatal */ }
      }
      paintSwatches();
    }

    function resetFgBg() {
      state.fg = DEFAULT_FG;
      state.bg = DEFAULT_BG;
      if (typeof eng.setColor === "function") {
        try { eng.setColor(state.fg); } catch (_e) { /* non-fatal */ }
      }
      if (typeof eng.setBgColor === "function") {
        try { eng.setBgColor(state.bg); } catch (_e) { /* non-fatal */ }
      }
      paintSwatches();
    }

    function driveTolerance(n) {
      state.tolerance = Math.round(clampNum(n, 0, 255, 32));
      // Exact public API is setFillTolerance; accept the documented
      // setTolerance alias only as a fallback for older engines.
      if (typeof eng.setFillTolerance === "function") {
        try { eng.setFillTolerance(state.tolerance); } catch (_e) { /* non-fatal */ }
      } else if (typeof eng.setTolerance === "function") {
        try { eng.setTolerance(state.tolerance); } catch (_e) { /* non-fatal */ }
      }
      if (tolInput && tolInput.value !== String(state.tolerance)) tolInput.value = String(state.tolerance);
    }

    function doUndo() {
      if (typeof eng.undo === "function") {
        try { eng.undo(); } catch (_e) { /* non-fatal */ }
      }
    }

    function doRedo() {
      if (typeof eng.redo === "function") {
        try { eng.redo(); } catch (_e) { /* non-fatal */ }
      }
    }

    function doZoomIn() {
      if (typeof eng.zoomIn === "function") {
        try { eng.zoomIn(); } catch (_e) { /* non-fatal */ }
      }
    }

    function doZoomOut() {
      if (typeof eng.zoomOut === "function") {
        try { eng.zoomOut(); } catch (_e) { /* non-fatal */ }
      }
    }

    function doZoomFit() {
      if (typeof eng.fit === "function") {
        try { eng.fit(); } catch (_e) { /* non-fatal */ }
      }
    }

    function doZoom100() {
      if (typeof eng.setZoom === "function") {
        try { eng.setZoom(1); } catch (_e) { /* non-fatal */ }
      }
    }

    // ---- build: tool bar (compact 4-col grid, 2 rows in the narrow rail) ----

    var toolSec = section("TOOLS");
    var toolGrid = el("div", "sketch-panels-tools");
    toolGrid.setAttribute("role", "toolbar");
    toolGrid.setAttribute("aria-label", "Sketch tools");
    for (var ti = 0; ti < TOOL_DEFS.length; ti++) {
      (function (def) {
        var b = el("button", "sketch-panels-tool");
        b.innerHTML = icon(def.icon, "<span>" + def.label + "</span>");
        b.type = "button";
        b.title = def.label + " (" + def.key + ")";
        b.setAttribute("data-testid", "sketch-tool-" + def.id);
        b.setAttribute("aria-pressed", "false");
        b.addEventListener("click", function () {
          driveTool(def.id);
        });
        toolBtns[def.id] = b;
        toolGrid.appendChild(b);
      })(TOOL_DEFS[ti]);
    }
    toolSec.appendChild(toolGrid);

    // ---- build: brush settings (sliders only, compact rows) ----

    var setSec = section("BRUSH");
    function sliderRow(labelText, min, max, step, testid, onInput) {
      var row = el("div", "sketch-panels-row");
      var lab = el("label", "sketch-panels-label", labelText);
      var slider = doc.createElement("input");
      slider.type = "range";
      slider.min = String(min);
      slider.max = String(max);
      slider.step = String(step);
      slider.className = "sketch-panels-slider";
      slider.setAttribute("data-testid", testid);
      var val = el("span", "sketch-panels-val", "");
      lab.appendChild(slider);
      row.appendChild(lab);
      row.appendChild(val);
      slider.addEventListener("input", function () {
        onInput(Number(slider.value));
      });
      setSec.appendChild(row);
      return { slider: slider, val: val };
    }

    var sizeCtl = sliderRow("Size", 1, 200, 1, "sketch-brush-size", driveSize);
    sizeSlider = sizeCtl.slider;
    sizeVal = sizeCtl.val;
    var opCtl = sliderRow("Opacity", 0, 100, 1, "sketch-brush-opacity", driveOpacity);
    opacitySlider = opCtl.slider;
    opacityVal = opCtl.val;
    var hardCtl = sliderRow("Hardness", 0, 100, 1, "sketch-brush-hardness", driveHardness);
    hardnessSlider = hardCtl.slider;
    hardnessVal = hardCtl.val;

    function syncHardnessEnabled() {
      if (!hardnessSlider) return;
      var applicable = !!HARDNESS_TOOLS[state.tool];
      hardnessSlider.disabled = !applicable;
      hardnessSlider.title = applicable ? "Brush hardness" : "Hardness applies to Brush/Pencil only";
    }

    // ---- build: color (SHORT by default; wheel/SV/HSL/RGB collapsed) ----

    var colSec = section("COLOR");
    var swRow = el("div", "sketch-panels-swatches");
    fgSwatch = el("button", "sketch-panels-swatch is-fg", "FG");
    fgSwatch.type = "button";
    fgSwatch.title = "Foreground color (click to edit)";
    fgSwatch.setAttribute("data-testid", "sketch-fg-swatch");
    fgSwatch.setAttribute("aria-label", "Foreground color (click to edit)");
    fgSwatch.addEventListener("click", function () {
      state.slot = "fg";
      paintSwatches();
    });
    bgSwatch = el("button", "sketch-panels-swatch is-bg", "BG");
    bgSwatch.type = "button";
    bgSwatch.title = "Background color (click to edit)";
    bgSwatch.setAttribute("data-testid", "sketch-bg-swatch");
    bgSwatch.setAttribute("aria-label", "Background color (click to edit)");
    bgSwatch.addEventListener("click", function () {
      state.slot = "bg";
      paintSwatches();
    });
    var swapBtn = el("button", "sketch-panels-mini comfymodal-secondary-btn"); swapBtn.innerHTML = icon("swap");
    swapBtn.type = "button";
    swapBtn.title = "Swap FG/BG (X)";
    swapBtn.setAttribute("data-testid", "sketch-swap-colors");
    swapBtn.setAttribute("aria-label", "Swap FG/BG");
    swapBtn.addEventListener("click", swapFgBg);
    var resetBtn = el("button", "sketch-panels-mini comfymodal-secondary-btn"); resetBtn.innerHTML = icon("reset");
    resetBtn.type = "button";
    resetBtn.title = "Reset black/white (D)";
    resetBtn.setAttribute("data-testid", "sketch-reset-colors");
    resetBtn.setAttribute("aria-label", "Reset black/white");
    resetBtn.addEventListener("click", resetFgBg);
    swRow.appendChild(fgSwatch);
    swRow.appendChild(swapBtn);
    swRow.appendChild(bgSwatch);
    swRow.appendChild(resetBtn);
    colSec.appendChild(swRow);

    var colRow = el("div", "sketch-panels-row");
    colorPicker = doc.createElement("input");
    colorPicker.type = "color";
    colorPicker.className = "sketch-panels-color";
    colorPicker.setAttribute("data-testid", "sketch-color-picker");
    colorPicker.title = "Pick color";
    colorPicker.value = DEFAULT_FG;
    colorPicker.addEventListener("input", function () {
      driveColor(colorPicker.value, state.slot);
      drawColorCanvases();
      if (hexInput) hexInput.value = normHex(colorPicker.value, DEFAULT_FG);
    });
    hexInput = doc.createElement("input");
    hexInput.type = "text";
    hexInput.className = "sketch-panels-hex";
    hexInput.setAttribute("data-testid", "sketch-color-hex");
    hexInput.setAttribute("spellcheck", "false");
    hexInput.setAttribute("maxlength", "7");
    hexInput.title = "Hex color, e.g. #ff0000";
    hexInput.value = DEFAULT_FG;
    hexInput.addEventListener("change", function () {
      driveColor(hexInput.value, state.slot);
      drawColorCanvases();
    });
    colRow.appendChild(colorPicker);
    colRow.appendChild(hexInput);
    colSec.appendChild(colRow);

    var presetRow = el("div", "sketch-panels-presets");
    ["#000000","#ffffff","#e53935","#fb8c00","#fdd835","#43a047","#1e88e5","#8e24aa","#795548","#90a4ae","#f48fb1","#26a69a"].forEach(function (color) {
      var p = el("button", "sketch-panels-preset"); p.type = "button"; p.style.background = color; p.title = color; p.setAttribute("aria-label", "Use " + color);
      p.addEventListener("click", function () { driveColor(color, state.slot); drawColorCanvases(); });
      presetRow.appendChild(p);
    });
    colSec.appendChild(presetRow);

    // Fill tolerance (kept simple: single 0..255 input).
    var tolRow = el("div", "sketch-panels-row");
    var tolLab = el("label", "sketch-panels-label", "Fill tolerance");
    tolInput = doc.createElement("input");
    tolInput.type = "number";
    tolInput.min = "0";
    tolInput.max = "255";
    tolInput.step = "1";
    tolInput.value = "32";
    tolInput.className = "sketch-panels-number";
    tolInput.setAttribute("data-testid", "sketch-fill-tolerance");
    tolInput.title = "Fill tolerance 0..255";
    tolInput.addEventListener("change", function () {
      driveTolerance(Number(tolInput.value));
    });
    tolLab.appendChild(tolInput);
    tolRow.appendChild(tolLab);
    colSec.appendChild(tolRow);

    // Advanced color: full HSV wheel + SV square + HSL/RGB inputs, collapsed
    // by default so the COLOR section stays SHORT in the narrow rail.
    advToggle = doc.createElement("button");
    advToggle.type = "button";
    advToggle.className = "sketch-panels-advanced-toggle";
    advToggle.setAttribute("data-testid", "sketch-advanced-color-toggle");
    advToggle.setAttribute("aria-expanded", "false");
    advToggle.setAttribute("aria-controls", "sketch-advanced-color-body");
    advToggle.innerHTML = '<span class="arrow">\u25b6</span><span>Advanced color</span>';
    advBody = el("div", "sketch-panels-advanced-body");
    advBody.id = "sketch-advanced-color-body";
    advBody.setAttribute("hidden", "");
    var colorBox = el("div", "sketch-panels-colorbox");
    wheelCanvas = doc.createElement("canvas"); wheelCanvas.width = 128; wheelCanvas.height = 128; wheelCanvas.setAttribute("aria-label", "Hue wheel");
    svCanvas = doc.createElement("canvas"); svCanvas.width = 128; svCanvas.height = 128; svCanvas.setAttribute("aria-label", "Saturation and value square");
    colorBox.appendChild(wheelCanvas); colorBox.appendChild(svCanvas); advBody.appendChild(colorBox);
    bindColorCanvas(wheelCanvas); bindColorCanvas(svCanvas);
    function advNumRow(names, testidPrefix, onCommit) {
      var row = el("div", "sketch-panels-rgbrow");
      var inputs = {};
      names.forEach(function (nm) {
        var lab = el("label", "sketch-panels-label", nm.toUpperCase());
        var inp = doc.createElement("input");
        inp.type = "number";
        inp.className = "sketch-panels-number";
        inp.setAttribute("data-testid", testidPrefix + "-" + nm);
        inp.value = "0";
        inp.addEventListener("change", function () { onCommit(inputs); });
        lab.appendChild(inp);
        row.appendChild(lab);
        inputs[nm] = inp;
      });
      advBody.appendChild(row);
      return inputs;
    }
    rgbInputs = advNumRow(["r", "g", "b"], "sketch-color-rgb", function (ins) {
      driveColor(rgbToHex(ins.r.value, ins.g.value, ins.b.value), state.slot);
      drawColorCanvases();
    });
    // Compact range hints on the number inputs (kept as attributes only).
    rgbInputs.r.min = "0"; rgbInputs.r.max = "255";
    rgbInputs.g.min = "0"; rgbInputs.g.max = "255";
    rgbInputs.b.min = "0"; rgbInputs.b.max = "255";
    hslInputs = advNumRow(["h", "s", "l"], "sketch-color-hsl", function (ins) {
      driveColor(hslToHex(ins.h.value, ins.s.value, ins.l.value), state.slot);
      drawColorCanvases();
    });
    hslInputs.h.min = "0"; hslInputs.h.max = "360";
    hslInputs.s.min = "0"; hslInputs.s.max = "100";
    hslInputs.l.min = "0"; hslInputs.l.max = "100";
    var advHint = el("div", "sketch-panels-help", "Wheel edits hue; square edits saturation/value.");
    advBody.appendChild(advHint);
    advToggle.addEventListener("click", function () {
      var open = advToggle.getAttribute("aria-expanded") === "true";
      advToggle.setAttribute("aria-expanded", open ? "false" : "true");
      if (open) advBody.setAttribute("hidden", "");
      else {
        advBody.removeAttribute("hidden");
        drawColorCanvases();
        paintAdvInputs(state.slot === "bg" ? state.bg : state.fg);
      }
    });
    colSec.appendChild(advToggle);
    colSec.appendChild(advBody);

    // ---- build: canvas controls (zoom mini-row + backup history; Clear/Save owned by shell) ----

    var cvSec = section("CANVAS");
    var zoomRow = el("div", "sketch-panels-zoomrow");
    function miniBtn(text, title, testid, onClick) {
      var b = el("button", "sketch-panels-mini comfymodal-secondary-btn", text);
      b.type = "button";
      b.title = title;
      b.setAttribute("data-testid", testid);
      b.addEventListener("click", onClick);
      zoomRow.appendChild(b);
      return b;
    }
     miniBtn("", "Zoom out (-)", "sketch-zoom-out", doZoomOut).innerHTML = icon("zoomOut");
    zoomLabel = el("span", "sketch-panels-zoomlabel", "");
    zoomLabel.setAttribute("data-testid", "sketch-zoom-label");
    zoomRow.appendChild(zoomLabel);
     miniBtn("", "Zoom in (+)", "sketch-zoom-in", doZoomIn).innerHTML = icon("zoomIn");
     miniBtn("", "Fit to view (0)", "sketch-zoom-fit", doZoomFit).innerHTML = icon("fit");
     miniBtn("100%", "Zoom 100% (1)", "sketch-zoom-100", doZoom100);
    cvSec.appendChild(zoomRow);

    var histRow = el("div", "sketch-panels-histrow");
    undoBtn = el("button", "sketch-panels-btn comfymodal-secondary-btn"); undoBtn.innerHTML = icon("undo", "Undo");
    undoBtn.type = "button";
    undoBtn.title = "Undo (Ctrl+Z)";
    undoBtn.setAttribute("data-testid", "sketch-undo");
    undoBtn.addEventListener("click", doUndo);
    redoBtn = el("button", "sketch-panels-btn comfymodal-secondary-btn"); redoBtn.innerHTML = icon("redo", "Redo");
    redoBtn.type = "button";
    redoBtn.title = "Redo (Ctrl+Shift+Z)";
    redoBtn.setAttribute("data-testid", "sketch-redo");
    redoBtn.addEventListener("click", doRedo);
    histRow.appendChild(undoBtn);
    histRow.appendChild(redoBtn);
    cvSec.appendChild(histRow);
    // Backup label so this compact row is not confused with the shelf footer
    // sticky action bar (other lane owns the primary undo/redo there).
    var histHint = el("div", "sketch-panels-help", "Backup — main undo/redo live in the shelf footer.");
    cvSec.appendChild(histHint);

    container.appendChild(root);

    // ---- sync from engine ----

    function syncFromEngine() {
      var s = readState(eng);
      if (typeof s.tool === "string" && toolBtns[s.tool]) {
        state.tool = s.tool;
      }
      var sz = Number(s.size);
      if (isFinite(sz) && sz > 0) state.size = Math.round(clampNum(sz, 1, 200, state.size));
      if (s.opacity !== undefined) {
        var so = opacityToSlider(s.opacity);
        if (isFinite(so)) state.opacity = so;
      }
      if (s.hardness !== undefined) {
        var sh = hardnessToSlider(s.hardness);
        if (isFinite(sh)) state.hardness = sh;
      }
      var fg = normHex(s.fg, null);
      if (fg) state.fg = fg;
      var bg = normHex(s.bg, null);
      if (bg) state.bg = bg;
      var activeHsv = rgbToHsv(hexToRgb(state.slot === "bg" ? state.bg : state.fg)); hue = activeHsv.h; sat = activeHsv.s; val = activeHsv.v;
      if (s.zoom !== undefined && s.zoom !== null) {
        var z = Number(s.zoom);
        if (isFinite(z)) state.zoom = z;
      }

      if (sizeSlider) sizeSlider.value = String(state.size);
      if (sizeVal) sizeVal.textContent = String(state.size) + "px";
      if (opacitySlider) opacitySlider.value = String(state.opacity);
      if (opacityVal) opacityVal.textContent = String(state.opacity) + "%";
      if (hardnessSlider) hardnessSlider.value = String(state.hardness);
      if (hardnessVal) hardnessVal.textContent = String(state.hardness) + "%";
      if (tolInput && doc.activeElement !== tolInput) tolInput.value = String(state.tolerance);
      paintToolButtons();
      paintSwatches();
      drawColorCanvases();
      paintZoom();
      paintUndoRedo();
      syncHardnessEnabled();
    }

    // Subscribe for active-state sync (exact hook only).
    if (typeof eng.onChange === "function") {
      try {
        var r = eng.onChange.call(eng, function () {
          syncFromEngine();
        });
        if (typeof r === "function") unsubscribe = r;
      } catch (_e) {
        /* optional hook */
      }
    }

    // ---- keyboard shortcuts (scoped: ignore editable fields) ----

    function isEditableTarget(t) {
      if (!t || !t.tagName) return false;
      var tag = String(t.tagName).toUpperCase();
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
      try {
        if (t.isContentEditable) return true;
      } catch (_e) {
        /* ignore */
      }
      return false;
    }

    function onKeyDown(ev) {
      // Scoped handler: dead once destroyed/unmounted, and never leaks to a
      // concurrent editor/panel. Removal in destroy() uses this same
      // function reference and document, so it detaches fully.
      if (!mounted) return;
      try {
        if (!container.isConnected) return;
      } catch (_e) {
        return;
      }
      try {
        if (!root.isConnected) return;
      } catch (_e) {
        return;
      }
      if (!ev || ev.defaultPrevented) return;
      try {
        var tgt = ev.target;
        if (tgt && typeof tgt.closest === "function") {
          var other = tgt.closest("[data-sketch-panels]");
          if (other && other !== root) return;
        }
      } catch (_e) {
        /* ignore */
      }
      if (isEditableTarget(ev.target)) return;
      var key = String(ev.key || "").toLowerCase();
      var ctrl = !!(ev.ctrlKey || ev.metaKey);

      if (ctrl && key === "z") {
        if (ev.shiftKey) doRedo();
        else doUndo();
        ev.preventDefault();
        return;
      }
      if (ctrl && key === "y") {
        doRedo();
        ev.preventDefault();
        return;
      }
      if (ctrl || ev.altKey) return;

      var map = { b: "brush", p: "pencil", e: "eraser", l: "line", r: "rectangle", c: "circle", g: "fill", i: "eyedropper" };
      if (map[key]) {
        driveTool(map[key]);
        ev.preventDefault();
        return;
      }
      if (key === "x") {
        swapFgBg();
        ev.preventDefault();
        return;
      }
      if (key === "d") {
        resetFgBg();
        ev.preventDefault();
        return;
      }
      if (key === "[") {
        driveSize(state.size - 1);
        ev.preventDefault();
        return;
      }
      if (key === "]") {
        driveSize(state.size + 1);
        ev.preventDefault();
        return;
      }
      if (key === "+" || key === "=") {
        doZoomIn();
        ev.preventDefault();
        return;
      }
      if (key === "-" || key === "_") {
        doZoomOut();
        ev.preventDefault();
        return;
      }
      if (key === "0") {
        doZoomFit();
        ev.preventDefault();
        return;
      }
      if (key === "1") {
        doZoom100();
        ev.preventDefault();
        return;
      }
    }

    if (keyboard && docAtMount.addEventListener) {
      docAtMount.addEventListener("keydown", onKeyDown);
    }

    function destroy() {
      mounted = false;
      try {
        if (docAtMount.removeEventListener) docAtMount.removeEventListener("keydown", onKeyDown);
      } catch (_e) {
        /* ignore */
      }
      try {
        if (typeof unsubscribe === "function") unsubscribe();
      } catch (_e) {
        /* ignore */
      }
      try {
        if (root.parentNode) root.parentNode.removeChild(root);
      } catch (_e) {
        /* ignore */
      }
    }

    syncFromEngine();

    return { destroy: destroy, syncFromEngine: syncFromEngine };
  }

  var api = { mountSketchPanels: mountSketchPanels, TOOLS: TOOL_DEFS };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  global.ComfyModalSketchPanels = api;
  if (typeof window !== "undefined") window.ComfyModalSketchPanels = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
