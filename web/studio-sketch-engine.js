// MIT attribution: Adapted from comfyui-comfysketch by Vitor Silva (Mexes1978)
// Upstream: https://github.com/Mexes1978/comfyui-comfysketch (MIT License)
// Upstream file: js/comfysketch.js (DrawingPad engine).
//
// Adapted: layered canvases + display composite (renderLayers), brush/pencil/
//   eraser/line/rectangle(square)/circle(ellipse)/fill(floodFill)/eyedropper
//   (pickColor), pressure-weighted dots (drawDot/drawLine/_drawDotAt/
//   drawBrushStroke round+hardness), stroke-buffer opacity accumulation,
//   history saveToHistory/undo/redo/loadFromHistory capped at 30, zoom/pan
//   (adjustZoom/updateCanvasTransform/screenToCanvasPos/getCanvasPos, wheel
//   zoom, space/middle-mouse pan, fit), keyboard shortcuts (handleKeyboard
//   with stopPropagation: B/P/E/L/C/R/G/I, Ctrl+Z/Y, +/-/0, [/], X, D).
// Replaced/omitted: ComfyUI node + app.registerExtension + LiteGraph wiring,
//   canvasDataWidget JPEG persistence (saveCanvasData), fullscreen overlay +
//   draggable-panel shell (DraggablePanel/Toolbar/ColorWheel/SizeOpacity/
//   Layers panels), selection + transform tools, mirror modes, extra brush
//   types (soft/airbrush/spray/marker/square-brush), theme code, SVG icons.
//   Layers are data-only here (no layer UI); Fixer B owns the layer panel and
//   drives this engine via the layer-canvas hooks below.

(function (global) {
  "use strict";

  var HISTORY_LIMIT = 30;
  var MIN_ZOOM = 0.25;
  var MAX_ZOOM = 8;

  // Tool aliases: upstream used 'draw' for brush and 'square' for rectangle.
  var TOOL_ALIASES = { draw: "brush", square: "rectangle", rect: "rectangle" };
  var VALID_TOOLS = ["brush", "pencil", "eraser", "line", "rectangle", "circle", "fill", "eyedropper"];

  function normalizeTool(tool) {
    if (!tool) return "brush";
    var t = String(tool).toLowerCase();
    if (TOOL_ALIASES[t]) t = TOOL_ALIASES[t];
    return VALID_TOOLS.indexOf(t) >= 0 ? t : "brush";
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function hexToRgb(hex) {
    var h = String(hex || "#000000").replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return {
      r: parseInt(h.slice(0, 2), 16) || 0,
      g: parseInt(h.slice(2, 4), 16) || 0,
      b: parseInt(h.slice(4, 6), 16) || 0,
    };
  }

  function rgbToHex(r, g, b) {
    function p(x) { return clamp(Math.round(x), 0, 255).toString(16).padStart(2, "0"); }
    return ("#" + p(r) + p(g) + p(b)).toUpperCase();
  }

  function makeCanvas(w, h) {
    var c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(w));
    c.height = Math.max(1, Math.round(h));
    return c;
  }

  /**
   * createSketchEngine(container, opts) — ComfySketch DrawingPad core,
   * adapted for the Studio shell. No ComfyUI/LiteGraph dependency.
   *
   * opts: { width, height, background }
   */
  function createSketchEngine(container, opts) {
    opts = opts || {};
    if (!container) throw new Error("createSketchEngine: container required");

    var state = {
      width: opts.width || 512,
      height: opts.height || 512,
      background: opts.background || "#FFFFFF",
      tool: "brush",
      brushSize: 8,
      opacity: 100,
      hardness: 100,
      color: "#000000",
      bgColor: "#FFFFFF",
      fillTolerance: 32,
      zoom: 1,
      panX: 0,
      panY: 0,
      spaceDown: false,
      panning: false,
      drawing: false,
      lastPoint: null,
      lastPressure: 0.5,
      strokePoints: [],
      strokeBuffer: null,
      strokeCtx: null,
      snapshot: null,
      layers: [],
      activeLayerIndex: 0,
      history: [],
      historyIndex: -1,
      changeListeners: [],
      destroyed: false,
    };

    // ---- DOM: preserve Studio test selectors ----
    var root = document.createElement("div");
    root.setAttribute("data-testid", "sketch-editor");
    root.style.cssText = "position:relative;width:100%;height:100%;overflow:hidden;outline:none;";
    root.tabIndex = 0;

    var wrap = document.createElement("div");
    wrap.setAttribute("data-testid", "sketch-canvas-wrap");
    wrap.style.cssText = "position:absolute;inset:0;overflow:hidden;display:flex;align-items:center;justify-content:center;background:#808080;touch-action:none;";

    var displayCanvas = makeCanvas(state.width, state.height);
    displayCanvas.setAttribute("data-testid", "sketch-canvas");
    displayCanvas.style.cssText = "image-rendering:auto;transform-origin:center center;cursor:crosshair;flex:none;";
    wrap.appendChild(displayCanvas);
    root.appendChild(wrap);
    container.appendChild(root);

    var baseCanvas = makeCanvas(state.width, state.height);
    // Single authoritative layer list: locked base lives at index 0 INSIDE
    // the engine (baseCanvas aliases state.layers[0].canvas). The store
    // drives add/remove/visibility/opacity/order hooks only and never keeps
    // a parallel composite.
    state.layers.push({ id: "base", canvas: baseCanvas, name: "Base", visible: true, opacity: 1, locked: true });
    try { if (baseCanvas.dataset) baseCanvas.dataset.layerId = "base"; } catch (_) {}

    // ---- layers (data-only; UI owned by Fixer B) ----
    var _layerSeq = 0;
    function nextLayerId(prefix) {
      _layerSeq += 1;
      return (prefix || "layer") + "-" + _layerSeq;
    }

    function isCanvasLike(x) {
      return !!x && typeof x === "object" && typeof x.width === "number" && typeof x.getContext === "function";
    }

    function syncBaseAliasFromLayers() {
      if (state.layers.length && state.layers[0] && state.layers[0].canvas) baseCanvas = state.layers[0].canvas;
    }

    function getLayerCanvases() {
      return state.layers.map(function (l) { return l.canvas; });
    }

    // Accepts (name, canvas) or (canvas) — the store calls with
    // (name, canvas); a bare canvas keeps backward compatibility.
    function addLayerCanvas(nameOrCanvas, canvasOrUndef) {
      var name = nameOrCanvas;
      var canvas = canvasOrUndef;
      if (isCanvasLike(nameOrCanvas) && canvasOrUndef === undefined) {
        canvas = nameOrCanvas;
        name = null;
      }
      var raw = canvas || makeCanvas(state.width, state.height);
      var id = null;
      try { id = raw.dataset && raw.dataset.layerId ? raw.dataset.layerId : null; } catch (_) { id = null; }
      if (!id) id = nextLayerId("layer");
      var c = raw;
      if (c.width !== state.width || c.height !== state.height) {
        var fit = makeCanvas(state.width, state.height);
        fit.getContext("2d").drawImage(c, 0, 0, state.width, state.height);
        c = fit;
      }
      try { if (c.dataset) c.dataset.layerId = id; } catch (_) {}
      var layer = { id: id, canvas: c, name: (typeof name === "string" && name) || ("Layer " + (state.layers.length + 1)), visible: true, opacity: 1, locked: false };
      state.layers.push(layer);
      state.activeLayerIndex = state.layers.length - 1;
      return layer;
    }

    // Resolve a layer by numeric index, string id, canvas reference, or
    // { id, canvas } wrapper. Returns -1 when unresolvable.
    function resolveLayerIndex(ref) {
      var i;
      if (ref == null) return state.activeLayerIndex;
      if (typeof ref === "number") return Math.floor(ref);
      if (isCanvasLike(ref)) {
        for (i = 0; i < state.layers.length; i++) {
          if (state.layers[i].canvas === ref) return i;
        }
        try {
          var did = ref.dataset && ref.dataset.layerId;
          if (did) {
            for (i = 0; i < state.layers.length; i++) {
              if (state.layers[i].id === did) return i;
            }
          }
        } catch (_) {}
        return -1;
      }
      if (typeof ref === "string") {
        for (i = 0; i < state.layers.length; i++) {
          if (state.layers[i].id === ref) return i;
        }
        return -1;
      }
      if (typeof ref === "object") {
        if (ref.id) {
          for (i = 0; i < state.layers.length; i++) {
            if (state.layers[i].id === ref.id) return i;
          }
        }
        if (ref.canvas) return resolveLayerIndex(ref.canvas);
        return -1;
      }
      return -1;
    }

    function removeLayerCanvas(ref) {
      var i = resolveLayerIndex(ref);
      if (state.layers.length <= 1 || i < 0 || i >= state.layers.length) return false;
      if (state.layers[i].locked) return false; // base is locked at index 0
      state.layers.splice(i, 1);
      state.activeLayerIndex = clamp(Math.min(i, state.layers.length - 1), 0, state.layers.length - 1);
      renderLayers();
      return true;
    }

    function setLayerVisibility(ref, visible) {
      var i = resolveLayerIndex(ref);
      if (i < 0 || i >= state.layers.length) return false;
      state.layers[i].visible = !!visible;
      return true;
    }

    function setLayerOpacity(ref, opacity) {
      var i = resolveLayerIndex(ref);
      if (i < 0 || i >= state.layers.length) return false;
      var n = Number(opacity);
      if (!isFinite(n)) n = 1;
      n = clamp(n, 0, 1);
      state.layers[i].opacity = n;
      return n;
    }

    // Reorder engine state.layers to match the given bottom->top order
    // (array of ids and/or canvases). Locked base is forced back to index 0.
    function setLayerOrder(order) {
      if (!order || !order.length) return false;
      var seen = {};
      var next = [];
      for (var k = 0; k < order.length; k++) {
        var idx = resolveLayerIndex(order[k]);
        if (idx < 0 || seen[idx]) continue;
        seen[idx] = true;
        next.push(state.layers[idx]);
      }
      for (var m = 0; m < state.layers.length; m++) {
        if (!seen[m]) next.push(state.layers[m]);
      }
      var activeId = state.layers[state.activeLayerIndex] && state.layers[state.activeLayerIndex].id;
      var basePos = -1;
      for (var b = 0; b < next.length; b++) {
        if (next[b] && (next[b].locked || next[b].id === "base")) { basePos = b; break; }
      }
      if (basePos > 0) {
        var base = next.splice(basePos, 1)[0];
        next.unshift(base);
      }
      state.layers = next;
      syncBaseAliasFromLayers();
      if (activeId != null) {
        for (var a = 0; a < state.layers.length; a++) {
          if (state.layers[a].id === activeId) { state.activeLayerIndex = a; break; }
        }
      }
      state.activeLayerIndex = clamp(state.activeLayerIndex, 0, Math.max(0, state.layers.length - 1));
      return true;
    }

    function getActiveLayer() {
      return state.layers[state.activeLayerIndex] || null;
    }

    function setActiveLayer(ref) {
      var i = resolveLayerIndex(ref);
      if (i >= 0 && i < state.layers.length) state.activeLayerIndex = i;
    }

    function resizeAll(w, h) {
      state.width = Math.max(1, Math.round(w));
      state.height = Math.max(1, Math.round(h));
      displayCanvas.width = state.width;
      displayCanvas.height = state.height;
      var nb = makeCanvas(state.width, state.height);
      nb.getContext("2d").drawImage(baseCanvas, 0, 0, state.width, state.height);
      baseCanvas = nb;
      if (state.layers.length && state.layers[0]) state.layers[0].canvas = baseCanvas;
      state.layers.forEach(function (l, idx) {
        if (idx === 0) return; // base already resized via the alias above
        var nc = makeCanvas(state.width, state.height);
        nc.getContext("2d").drawImage(l.canvas, 0, 0, state.width, state.height);
        l.canvas = nc;
      });
      updateCanvasTransform();
      renderLayers();
    }

    // ---- composite (upstream renderLayers) ----
    function renderLayers() {
      if (state.destroyed) return;
      var ctx = displayCanvas.getContext("2d");
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = state.background;
      ctx.fillRect(0, 0, state.width, state.height);
      // Unified ownership: base is state.layers[0]; composite the single
      // list bottom->top (no separate baseCanvas pass, no double-draw).
      for (var i = 0; i < state.layers.length; i++) {
        var layer = state.layers[i];
        if (!layer.visible) continue;
        ctx.globalAlpha = typeof layer.opacity === "number" ? layer.opacity : 1;
        ctx.drawImage(layer.canvas, 0, 0);
        // Stroke buffer on top of the active layer while drawing (upstream).
        if (i === state.activeLayerIndex && state.strokeBuffer) {
          ctx.globalAlpha = (state.opacity / 100) * ctx.globalAlpha;
          // ctx.globalAlpha above was already layer opacity; recompute explicitly:
          ctx.globalAlpha = (state.opacity / 100) * (typeof layer.opacity === "number" ? layer.opacity : 1);
          ctx.drawImage(state.strokeBuffer, 0, 0);
        }
      }
      ctx.globalAlpha = 1;
    }

    function emitChange() {
      state.changeListeners.forEach(function (cb) {
        try { cb(); } catch (_) { /* ignore */ }
      });
    }

    // ---- history (upstream saveToHistory/undo/redo/loadFromHistory, cap 30) ----
    function saveToHistory() {
      var snapshot = state.layers.map(function (l) {
        return { imageData: l.canvas.toDataURL(), id: l.id, name: l.name, visible: l.visible, opacity: l.opacity, locked: !!l.locked };
      });
      state.history = state.history.slice(0, state.historyIndex + 1);
      state.history.push({ layers: snapshot, activeIndex: state.activeLayerIndex });
      if (state.history.length > HISTORY_LIMIT) state.history.shift();
      state.historyIndex = state.history.length - 1;
    }

    function loadFromHistory() {
      var entry = state.history[state.historyIndex];
      if (!entry) return;
      var pending = entry.layers.length;
      if (pending === 0) { renderLayers(); return; }
      var next = [];
      entry.layers.forEach(function (ld) {
        var c = makeCanvas(state.width, state.height);
        var img = new Image();
        img.onload = function () {
          c.getContext("2d").drawImage(img, 0, 0);
          pending--;
          if (pending === 0) {
            state.layers = next;
            restoreBaseInvariant();
            state.activeLayerIndex = clamp(entry.activeIndex, 0, Math.max(0, next.length - 1));
            renderLayers();
            emitChange();
          }
        };
        img.onerror = function () {
          pending--;
          if (pending === 0) {
            state.layers = next;
            restoreBaseInvariant();
            state.activeLayerIndex = clamp(entry.activeIndex, 0, Math.max(0, next.length - 1));
            renderLayers();
            emitChange();
          }
        };
        img.src = ld.imageData;
        next.push({ id: ld.id, canvas: c, name: ld.name, visible: ld.visible, opacity: ld.opacity, locked: !!ld.locked });
      });
    }

    function restoreBaseInvariant() {
      if (!state.layers.length) return;
      var basePos = -1;
      for (var b = 0; b < state.layers.length; b++) {
        if (state.layers[b] && (state.layers[b].locked || state.layers[b].id === "base")) { basePos = b; break; }
      }
      if (basePos > 0) {
        var base = state.layers.splice(basePos, 1)[0];
        state.layers.unshift(base);
      }
      state.layers[0].locked = true;
      syncBaseAliasFromLayers();
    }

    function undo() {
      if (state.historyIndex > 0) { state.historyIndex--; loadFromHistory(); return true; }
      return false;
    }

    function redo() {
      if (state.historyIndex < state.history.length - 1) { state.historyIndex++; loadFromHistory(); return true; }
      return false;
    }

    // ---- zoom / pan (upstream adjustZoom/updateCanvasTransform/fitToView) ----
    function updateCanvasTransform() {
      displayCanvas.style.transform = "scale(" + state.zoom + ") translate(" + state.panX + "px, " + state.panY + "px)";
    }

    function setZoom(z) {
      state.zoom = clamp(z, MIN_ZOOM, MAX_ZOOM);
      updateCanvasTransform();
      emitChange();
    }

    function adjustZoom(delta) {
      setZoom(state.zoom + delta);
    }

    function zoomIn() { adjustZoom(0.25); }
    function zoomOut() { adjustZoom(-0.25); }
    function zoom100() {
      state.zoom = 1; state.panX = 0; state.panY = 0;
      updateCanvasTransform();
      emitChange();
    }

    function fit() {
      var cw = wrap.clientWidth - 40;
      var ch = wrap.clientHeight - 40;
      if (cw <= 0 || ch <= 0) { zoom100(); return; }
      state.zoom = Math.min(cw / state.width, ch / state.height, 1);
      state.zoom = clamp(state.zoom, MIN_ZOOM, MAX_ZOOM);
      state.panX = 0; state.panY = 0;
      updateCanvasTransform();
      emitChange();
    }

    // Upstream screenToCanvasPos: map client coords through the displayed rect.
    function screenToCanvasPos(clientX, clientY) {
      var rect = displayCanvas.getBoundingClientRect();
      return {
        x: (clientX - rect.left) * (state.width / rect.width),
        y: (clientY - rect.top) * (state.height / rect.height),
      };
    }

    function getCanvasPos(e) {
      return screenToCanvasPos(e.clientX, e.clientY);
    }

    // ---- brush core (upstream drawDot/_drawDotAt/drawLine/drawBrushStroke) ----
    function brushTarget() {
      var layer = getActiveLayer();
      if (!layer) return null;
      if (state.strokeBuffer) return { ctx: state.strokeCtx, buffered: true };
      return { ctx: layer.canvas.getContext("2d"), buffered: false };
    }

    function drawBrushStroke(ctx, x, y, size) {
      ctx.fillStyle = state.color;
      var hardness = clamp(state.hardness, 1, 100) / 100;
      if (hardness < 1) {
        var c = hexToRgb(state.color);
        var g = ctx.createRadialGradient(x, y, 0, x, y, Math.max(0.5, size / 2));
        var core = hardness * 0.8;
        g.addColorStop(0, state.color);
        g.addColorStop(clamp(core, 0, 1), state.color);
        g.addColorStop(clamp(core + (1 - core) * 0.5, 0, 1), "rgba(" + c.r + "," + c.g + "," + c.b + ",0.5)");
        g.addColorStop(1, "rgba(" + c.r + "," + c.g + "," + c.b + ",0)");
        ctx.fillStyle = g;
      }
      ctx.beginPath();
      ctx.arc(x, y, Math.max(0.5, size / 2), 0, Math.PI * 2);
      ctx.fill();
    }

    function drawDotAt(ctx, x, y, size) {
      if (state.tool === "eraser") {
        ctx.globalCompositeOperation = "destination-out";
        ctx.beginPath(); ctx.arc(x, y, size / 2, 0, Math.PI * 2); ctx.fill();
        ctx.globalCompositeOperation = "source-over";
      } else if (state.tool === "pencil") {
        // Upstream Wu anti-aliased 1px pencil.
        ctx.fillStyle = state.color;
        var fx = Math.floor(x), fy = Math.floor(y);
        var ax = x - fx, ay = y - fy;
        var o = state.opacity / 100;
        ctx.globalAlpha = o * (1 - ax) * (1 - ay); ctx.fillRect(fx, fy, 1, 1);
        ctx.globalAlpha = o * ax * (1 - ay); ctx.fillRect(fx + 1, fy, 1, 1);
        ctx.globalAlpha = o * (1 - ax) * ay; ctx.fillRect(fx, fy + 1, 1, 1);
        ctx.globalAlpha = o * ax * ay; ctx.fillRect(fx + 1, fy + 1, 1, 1);
        ctx.globalAlpha = o;
      } else {
        drawBrushStroke(ctx, x, y, size);
      }
    }

    function dotSize(pressure) {
      if (state.tool === "eraser") return state.brushSize * 2;
      if (state.tool === "pencil") return 1;
      return state.brushSize * (0.3 + pressure * 0.7);
    }

    function drawDot(pos, pressure) {
      var t = brushTarget();
      if (!t) return;
      if (!t.buffered) t.ctx.globalAlpha = state.opacity / 100;
      drawDotAt(t.ctx, pos.x, pos.y, dotSize(pressure));
      if (!t.buffered) t.ctx.globalAlpha = 1;
    }

    function drawLine(from, to, pFrom, pTo) {
      var t = brushTarget();
      if (!t) return;
      var ctx = t.ctx;
      var dist = Math.hypot(to.x - from.x, to.y - from.y);
      var spacing = state.tool === "pencil" ? 0.5 : Math.max(0.5, state.brushSize * 0.15);
      var steps = Math.max(1, Math.ceil(dist / spacing));
      if (!t.buffered) ctx.globalAlpha = state.opacity / 100;
      for (var i = 0; i <= steps; i++) {
        var k = i / steps;
        var p = pFrom + (pTo - pFrom) * k;
        drawDotAt(ctx, from.x + (to.x - from.x) * k, from.y + (to.y - from.y) * k, dotSize(p));
      }
      if (!t.buffered) ctx.globalAlpha = 1;
    }

    function drawStraightLine(from, to) {
      var layer = getActiveLayer();
      if (!layer) return;
      var ctx = layer.canvas.getContext("2d");
      ctx.globalAlpha = state.opacity / 100;
      ctx.strokeStyle = state.tool === "eraser" ? "#000000" : state.color;
      if (state.tool === "eraser") ctx.globalCompositeOperation = "destination-out";
      ctx.lineWidth = state.brushSize;
      ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y); ctx.stroke();
      ctx.globalCompositeOperation = "source-over";
      ctx.globalAlpha = 1;
    }

    function drawCircle(center, edge, perfect) {
      var layer = getActiveLayer();
      if (!layer) return;
      var ctx = layer.canvas.getContext("2d");
      ctx.globalAlpha = state.opacity / 100;
      ctx.strokeStyle = state.color;
      ctx.lineWidth = state.brushSize;
      var rx = Math.abs(edge.x - center.x);
      var ry = Math.abs(edge.y - center.y);
      if (perfect) { var r = Math.max(rx, ry); rx = ry = r; }
      ctx.beginPath();
      ctx.ellipse(center.x, center.y, Math.max(0.5, rx), Math.max(0.5, ry), 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    function drawRectangle(start, end, perfect) {
      var layer = getActiveLayer();
      if (!layer) return;
      var ctx = layer.canvas.getContext("2d");
      ctx.globalAlpha = state.opacity / 100;
      ctx.strokeStyle = state.color;
      ctx.lineWidth = state.brushSize;
      var w = end.x - start.x;
      var h = end.y - start.y;
      if (perfect) {
        var s = Math.max(Math.abs(w), Math.abs(h));
        w = w < 0 ? -s : s;
        h = h < 0 ? -s : s;
      }
      ctx.strokeRect(start.x, start.y, w, h);
      ctx.globalAlpha = 1;
    }

    // Upstream floodFill (scanline stack, tolerance) on the active layer.
    function floodFill(pos) {
      var layer = getActiveLayer();
      if (!layer) return;
      var ctx = layer.canvas.getContext("2d");
      var sx = clamp(Math.floor(pos.x), 0, state.width - 1);
      var sy = clamp(Math.floor(pos.y), 0, state.height - 1);
      var imageData;
      try {
        imageData = ctx.getImageData(0, 0, state.width, state.height);
      } catch (_) { return; }
      var data = imageData.data;
      var startIdx = (sy * state.width + sx) * 4;
      var startR = data[startIdx], startG = data[startIdx + 1], startB = data[startIdx + 2], startA = data[startIdx + 3];
      var fill = hexToRgb(state.color);
      var fillA = Math.round((state.opacity / 100) * 255);
      if (startR === fill.r && startG === fill.g && startB === fill.b && startA === fillA) return;
      var tol = state.fillTolerance || 32;
      function matches(idx) {
        return Math.abs(data[idx] - startR) <= tol &&
          Math.abs(data[idx + 1] - startG) <= tol &&
          Math.abs(data[idx + 2] - startB) <= tol &&
          Math.abs(data[idx + 3] - startA) <= tol;
      }
      var stack = [[sx, sy]];
      var visited = new Set();
      while (stack.length) {
        var cur = stack.pop();
        var x = cur[0], y = cur[1];
        if (x < 0 || x >= state.width || y < 0 || y >= state.height) continue;
        var key = x + "," + y;
        if (visited.has(key)) continue;
        var idx = (y * state.width + x) * 4;
        if (!matches(idx)) continue;
        visited.add(key);
        data[idx] = fill.r; data[idx + 1] = fill.g; data[idx + 2] = fill.b; data[idx + 3] = fillA;
        stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
      }
      ctx.putImageData(imageData, 0, 0);
      renderLayers();
      saveToHistory();
      emitChange();
    }

    function pickColor(pos) {
      var x = clamp(Math.floor(pos.x), 0, state.width - 1);
      var y = clamp(Math.floor(pos.y), 0, state.height - 1);
      var px = displayCanvas.getContext("2d").getImageData(x, y, 1, 1).data;
      state.color = rgbToHex(px[0], px[1], px[2]);
      return state.color;
    }

    function saveSnapshot() {
      var layer = getActiveLayer();
      if (layer) {
        try {
          state.snapshot = layer.canvas.getContext("2d").getImageData(0, 0, state.width, state.height);
        } catch (_) { state.snapshot = null; }
      }
    }

    function restoreSnapshot() {
      var layer = getActiveLayer();
      if (state.snapshot && layer) layer.canvas.getContext("2d").putImageData(state.snapshot, 0, 0);
    }

    // ---- pointer input (upstream onPointerDown/Move/Up) ----
    function beginStroke(pos, pressure) {
      state.drawing = true;
      state.lastPoint = pos;
      state.lastPressure = pressure;
      state.strokePoints = [{ x: pos.x, y: pos.y, pressure: pressure }];
      // Stroke buffer avoids opacity accumulation within one stroke (upstream).
      if (state.tool === "brush") {
        state.strokeBuffer = makeCanvas(state.width, state.height);
        state.strokeCtx = state.strokeBuffer.getContext("2d");
        state.strokeCtx.globalAlpha = 1;
      } else {
        state.strokeBuffer = null;
        state.strokeCtx = null;
      }
      if (state.tool === "brush" || state.tool === "eraser" || state.tool === "pencil") {
        drawDot(pos, pressure);
        renderLayers();
      } else {
        saveSnapshot();
      }
    }

    function commitStrokeBuffer() {
      if (state.strokeBuffer && state.tool === "brush") {
        var layer = getActiveLayer();
        if (layer) {
          var ctx = layer.canvas.getContext("2d");
          ctx.globalAlpha = state.opacity / 100;
          ctx.drawImage(state.strokeBuffer, 0, 0);
          ctx.globalAlpha = 1;
        }
        state.strokeBuffer = null;
        state.strokeCtx = null;
      }
    }

    function onPointerDown(e) {
      if (state.destroyed) return;
      if (e.button === 1 || state.spaceDown) { startPan(e); return; }
      if (e.button !== 0 && e.pointerType === "mouse") return;
      e.preventDefault();
      try { root.focus({ preventScroll: true }); } catch (_) { try { root.focus(); } catch (_) {} }
      var pos = getCanvasPos(e);
      state.shiftKey = !!e.shiftKey;
      if (state.tool === "eyedropper") { pickColor(pos); setTool("brush"); return; }
      if (state.tool === "fill") { floodFill(pos); return; }
      beginStroke(pos, e.pressure == null ? 0.5 : e.pressure);
      try { displayCanvas.setPointerCapture(e.pointerId); } catch (_) {}
    }

    function onPointerMove(e) {
      if (state.destroyed) return;
      if (state.panning) {
        state.panX += (e.clientX - state.lastPan.x) / state.zoom;
        state.panY += (e.clientY - state.lastPan.y) / state.zoom;
        state.lastPan = { x: e.clientX, y: e.clientY };
        updateCanvasTransform();
        return;
      }
      if (!state.drawing) return;
      var pos = getCanvasPos(e);
      var pressure = e.pressure == null ? 0.5 : e.pressure;
      state.shiftKey = !!e.shiftKey;
      if (state.tool === "brush" || state.tool === "eraser" || state.tool === "pencil") {
        state.strokePoints.push({ x: pos.x, y: pos.y, pressure: pressure });
        drawLine(state.lastPoint, pos, state.lastPressure, pressure);
        state.lastPoint = pos;
        state.lastPressure = pressure;
        renderLayers();
      } else {
        restoreSnapshot();
        if (state.tool === "line") drawStraightLine(state.lastPoint, pos);
        else if (state.tool === "circle") drawCircle(state.lastPoint, pos, state.shiftKey);
        else if (state.tool === "rectangle") drawRectangle(state.lastPoint, pos, state.shiftKey);
        renderLayers();
      }
    }

    function onPointerUp(e) {
      if (state.destroyed) return;
      if (state.panning) { stopPan(); return; }
      if (!state.drawing) return;
      if (e && (state.tool === "line" || state.tool === "circle" || state.tool === "rectangle")) {
        var pos = getCanvasPos(e);
        state.shiftKey = !!e.shiftKey;
        restoreSnapshot();
        if (state.tool === "line") drawStraightLine(state.lastPoint, pos);
        else if (state.tool === "circle") drawCircle(state.lastPoint, pos, state.shiftKey);
        else if (state.tool === "rectangle") drawRectangle(state.lastPoint, pos, state.shiftKey);
      }
      commitStrokeBuffer();
      state.drawing = false;
      state.lastPoint = null;
      state.strokePoints = [];
      renderLayers();
      saveToHistory();
      emitChange();
    }

    function startPan(e) {
      state.panning = true;
      state.lastPan = { x: e.clientX, y: e.clientY };
      displayCanvas.style.cursor = "grabbing";
      try { displayCanvas.setPointerCapture(e.pointerId); } catch (_) {}
    }

    function stopPan() {
      state.panning = false;
      state.lastPan = null;
      updateCursor();
    }

    function onWheel(e) {
      if (state.destroyed) return;
      e.preventDefault();
      adjustZoom(e.deltaY > 0 ? -0.1 : 0.1);
    }

    function updateCursor() {
      if (state.panning || state.spaceDown) displayCanvas.style.cursor = "grab";
      else if (state.tool === "eyedropper") displayCanvas.style.cursor = "copy";
      else displayCanvas.style.cursor = "crosshair";
    }

    // ---- keyboard (upstream handleKeyboard; stop propagation like upstream) ----
    function handleKeyboard(e) {
      if (!e || state.destroyed) return;
      var tag = e.target && e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      // Keep sketch keys from reaching the Studio shell / canvas graph.
      e.stopPropagation();
      var key = (e.key || "").toLowerCase();
      if ((e.ctrlKey || e.metaKey) && key === "z" && !e.shiftKey) { e.preventDefault(); undo(); return; }
      if ((e.ctrlKey || e.metaKey) && (key === "y" || (key === "z" && e.shiftKey))) { e.preventDefault(); redo(); return; }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      switch (key) {
        case "b": setTool("brush"); break;
        case "p": setTool("pencil"); break;
        case "e": setTool("eraser"); break;
        case "l": setTool("line"); break;
        case "c": setTool("circle"); break;
        case "r": setTool("rectangle"); break;
        case "g": setTool("fill"); break;
        case "i": setTool("eyedropper"); break;
        case "x": swapColors(); break;
        case "d":
          state.color = "#000000"; state.bgColor = "#FFFFFF";
          emitChange();
          break;
        case "0": zoom100(); break;
        case "-": case "_": adjustZoom(-0.25); break;
        case "=": case "+": adjustZoom(0.25); break;
        case "[": setSize(state.brushSize - 2); break;
        case "]": setSize(state.brushSize + 2); break;
        case " ": e.preventDefault(); break;
        default: break;
      }
    }

    function onKeyDown(e) {
      if (e.key === " " && !state.spaceDown) {
        var tag = e.target && e.target.tagName;
        if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
          state.spaceDown = true;
          updateCursor();
        }
      }
      // Only handle shortcuts when focus is inside the editor.
      if (root.contains(e.target) || e.target === document.body) handleKeyboard(e);
    }

    function onKeyUp(e) {
      if (e.key === " ") { state.spaceDown = false; if (!state.panning) updateCursor(); }
    }

    function onMouseDownCapture(e) {
      // Middle-mouse pan anywhere over the canvas.
      if (e.button === 1 && wrap.contains(e.target)) { e.preventDefault(); startPan(e); }
    }

    // ---- public setters ----
    function setTool(tool) {
      state.tool = normalizeTool(tool);
      updateCursor();
      emitChange();
      return state.tool;
    }

    function setSize(px) {
      state.brushSize = clamp(Math.round(px) || 1, 1, 100);
      emitChange();
      return state.brushSize;
    }

    function setOpacity(pct) {
      state.opacity = clamp(Math.round(pct), 1, 100);
      emitChange();
      return state.opacity;
    }

    function setHardness(pct) {
      state.hardness = clamp(Math.round(pct), 1, 100);
      emitChange();
      return state.hardness;
    }

    function setColor(hex) {
      if (/^#?[0-9A-Fa-f]{6}$/.test(hex)) {
        state.color = (hex[0] === "#" ? hex : "#" + hex).toUpperCase();
      }
      emitChange();
      return state.color;
    }

    function setBgColor(hex) {
      if (/^#?[0-9A-Fa-f]{6}$/.test(hex)) {
        state.bgColor = (hex[0] === "#" ? hex : "#" + hex).toUpperCase();
      }
      emitChange();
      return state.bgColor;
    }

    function swapColors() {
      var t = state.color;
      state.color = state.bgColor;
      state.bgColor = t;
      emitChange();
    }

    function setBackground(hex) {
      state.background = hex;
      renderLayers();
      saveToHistory();
      emitChange();
    }

    // ---- base image / export ----
    function setBaseImage(source, w, h) {
      if (source === "blank" || source == null) {
        if (w && h) resizeAll(w, h);
        baseCanvas.getContext("2d").clearRect(0, 0, state.width, state.height);
        if (state.layers.length && state.layers[0]) state.layers[0].canvas = baseCanvas;
        renderLayers();
        saveToHistory();
        emitChange();
        return Promise.resolve(true);
      }
      return new Promise(function (resolve, reject) {
        var img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = function () {
          var tw = w || img.naturalWidth || state.width;
          var th = h || img.naturalHeight || state.height;
          resizeAll(tw, th);
          var ctx = baseCanvas.getContext("2d");
          ctx.clearRect(0, 0, state.width, state.height);
          ctx.drawImage(img, 0, 0, state.width, state.height);
          if (state.layers.length && state.layers[0]) state.layers[0].canvas = baseCanvas;
          renderLayers();
          saveToHistory();
          emitChange();
          resolve(true);
        };
        img.onerror = function (err) { reject(err || new Error("setBaseImage: load failed")); };
        img.src = source;
      });
    }

    function flatten() {
      // Commit any in-progress stroke so the active buffer is included.
      commitStrokeBuffer();
      var out = makeCanvas(state.width, state.height);
      var ctx = out.getContext("2d");
      ctx.fillStyle = state.background;
      ctx.fillRect(0, 0, state.width, state.height);
      // Unified ownership: base is state.layers[0]; no separate base pass.
      state.layers.forEach(function (l) {
        if (!l.visible) return;
        ctx.globalAlpha = typeof l.opacity === "number" ? l.opacity : 1;
        ctx.drawImage(l.canvas, 0, 0);
      });
      ctx.globalAlpha = 1;
      return out;
    }

    // Intentional Studio source-image contract: PNG flatten output
    // (NOT upstream JPEG .85) — keep lossless for downstream compositing.
    function flattenToDataURL() {
      return flatten().toDataURL("image/png");
    }

    // Intentional Studio source-image contract: PNG blob output
    // (NOT upstream JPEG .85).
    function flattenToBlob() {
      var canvas = flatten();
      return new Promise(function (resolve, reject) {
        if (canvas.toBlob) canvas.toBlob(function (b) { b ? resolve(b) : reject(new Error("toBlob failed")); }, "image/png");
        else {
          // Fallback: dataURL -> Blob.
          try {
            var parts = canvas.toDataURL("image/png").split(",");
            var bin = atob(parts[1]);
            var arr = new Uint8Array(bin.length);
            for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
            resolve(new Blob([arr], { type: "image/png" }));
          } catch (err) { reject(err); }
        }
      });
    }

    function onChange(cb) {
      if (typeof cb === "function") state.changeListeners.push(cb);
      return function () {
        var i = state.changeListeners.indexOf(cb);
        if (i >= 0) state.changeListeners.splice(i, 1);
      };
    }

    function getState() {
      return {
        tool: state.tool,
        brushSize: state.brushSize,
        opacity: state.opacity,
        hardness: state.hardness,
        color: state.color,
        bgColor: state.bgColor,
        zoom: state.zoom,
        panX: state.panX,
        panY: state.panY,
        width: state.width,
        height: state.height,
        layerCount: state.layers.length,
        activeLayerIndex: state.activeLayerIndex,
        canUndo: state.historyIndex > 0,
        canRedo: state.historyIndex < state.history.length - 1,
      };
    }

    function destroy() {
      if (state.destroyed) return;
      state.destroyed = true;
      displayCanvas.removeEventListener("pointerdown", onPointerDown);
      displayCanvas.removeEventListener("pointermove", onPointerMove);
      displayCanvas.removeEventListener("pointerup", onPointerUp);
      displayCanvas.removeEventListener("pointercancel", onPointerUp);
      wrap.removeEventListener("wheel", onWheel);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("keyup", onKeyUp, true);
      document.removeEventListener("mousedown", onMouseDownCapture, true);
      state.changeListeners = [];
      if (root.parentNode) root.parentNode.removeChild(root);
    }

    // ---- wire up ----
    displayCanvas.addEventListener("pointerdown", onPointerDown);
    displayCanvas.addEventListener("pointermove", onPointerMove);
    displayCanvas.addEventListener("pointerup", onPointerUp);
    displayCanvas.addEventListener("pointercancel", onPointerUp);
    wrap.addEventListener("wheel", onWheel, { passive: false });
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("keyup", onKeyUp, true);
    document.addEventListener("mousedown", onMouseDownCapture, true);

    // Locked base at index 0 is created with the engine; no extra layer here.
    updateCanvasTransform();
    renderLayers();
    saveToHistory();

    return {
      // lifecycle / image
      setBaseImage: setBaseImage,
      flattenToBlob: flattenToBlob,
      flattenToDataURL: flattenToDataURL,
      destroy: destroy,
      onChange: onChange,
      // history
      undo: undo,
      redo: redo,
      saveToHistory: saveToHistory,
      // tools + settings
      setTool: setTool,
      getTool: function () { return state.tool; },
      setSize: setSize,
      setOpacity: setOpacity,
      setHardness: setHardness,
      setColor: setColor,
      getColor: function () { return state.color; },
      setBgColor: setBgColor,
      getBgColor: function () { return state.bgColor; },
      swapColors: swapColors,
      setBackground: setBackground,
      setFillTolerance: function (v) { state.fillTolerance = clamp(Math.round(v) || 0, 0, 100); },
      // zoom / pan
      setZoom: setZoom,
      zoomIn: zoomIn,
      zoomOut: zoomOut,
      zoom100: zoom100,
      fit: fit,
      getZoom: function () { return state.zoom; },
      getPan: function () { return { x: state.panX, y: state.panY }; },
      setPan: function (x, y) { state.panX = x || 0; state.panY = y || 0; updateCanvasTransform(); },
      // layer-canvas hooks for Fixer B (no layer UI here)
      getLayerCanvases: getLayerCanvases,
      addLayerCanvas: addLayerCanvas,
      removeLayerCanvas: removeLayerCanvas,
      setLayerVisibility: setLayerVisibility,
      setLayerOpacity: setLayerOpacity,
      setLayerOrder: setLayerOrder,
      resolveLayerIndex: resolveLayerIndex,
      getActiveLayer: getActiveLayer,
      setActiveLayer: setActiveLayer,
      renderLayers: renderLayers,
      screenToCanvasPos: screenToCanvasPos,
      getState: getState,
      // test hooks
      root: root,
      displayCanvas: displayCanvas,
    };
  }

  var api = { createSketchEngine: createSketchEngine };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.ComfyStudioSketchEngine = api;
  global.createSketchEngine = global.createSketchEngine || createSketchEngine;
})(typeof window !== "undefined" ? window : this);
