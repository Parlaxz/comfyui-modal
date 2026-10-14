"use strict";
/**
 * studio-sketch-layers.js — Sketch layer UI/state module (Phase 6).
 *
 * Adapted from ComfySketch LayersPanel behavior (simplified): plain sidebar
 * panel, no floating/draggable architecture.
 *
 * Layer model: { id, name, canvas, visible, opacity, locked }
 *   - index 0 is always the base entry: locked, not deletable, stays bottom.
 *   - layers draw above base (array order = bottom -> top).
 *
 * Engine hook contract (all optional / defensive — never crashes when the
 * DrawingPad core from Fixer A is absent or partial):
 *   engine.getLayerCanvases() -> Array<HTMLCanvasElement>
 *   engine.addLayerCanvas(canvas) -> void
 *   engine.removeLayerCanvas(idOrCanvas) -> void
 *   engine.renderLayers() -> void
 *   engine.onChange(cb) -> unsubscribe fn (optional)
 *
 * History snapshot contract (first available wins, all optional):
 *   opts.onSnapshot(layers) -> void
 *   engine.saveToHistory() / engine.snapshot() / engine.pushHistory() /
 *   engine.saveSnapshot() / engine.historyPush() / engine.commitHistory()
 */

(function (global) {
  // Lucide icons (ISC license): https://lucide.dev/license
  var LUCIDE = {
    eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    hidden: '<path d="m3 3 18 18M10.6 5.1A10 10 0 0 1 12 5c7 0 10 7 10 7a16 16 0 0 1-3.2 4.4M6.2 6.2A13 13 0 0 0 2 12s3 7 10 7a10 10 0 0 0 1.4-.1"/>',
    up: '<path d="m5 15 7-7 7 7"/>', down: '<path d="m5 9 7 7 7-7"/>', duplicate: '<rect x="8" y="8" width="12" height="12" rx="1"/><path d="M4 16V4a1 1 0 0 1 1-1h12"/>',
    merge: '<path d="m3 16 4 4 4-4M7 20V4M11 4h10"/>', delete: '<path d="M5 12h14"/>', lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>', plus:'<path d="M12 5v14M5 12h14"/>'
  };
  function icon(name) { return '<svg class="sketch-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (LUCIDE[name] || "") + '</svg>'; }
  var BASE_ID = "base";

  var _seq = 0;
  function nextId(prefix) {
    _seq += 1;
    return (prefix || "layer") + "-" + Date.now().toString(36) + "-" + _seq;
  }

  function clamp01(v) {
    var n = Number(v);
    if (!isFinite(n)) return 1;
    if (n < 0) return 0;
    if (n > 1) return 1;
    return n;
  }

  function isBase(layer) {
    return !!layer && (layer.id === BASE_ID || layer.locked === true);
  }

  function resolveSize(engine, opts) {
    var w = opts && opts.width != null ? Number(opts.width) : NaN;
    var h = opts && opts.height != null ? Number(opts.height) : NaN;
    if (!isFinite(w) || w <= 0) {
      w = Number(engine && (engine.width || (engine.size && engine.size.width))) || 512;
    }
    if (!isFinite(h) || h <= 0) {
      h = Number(engine && (engine.height || (engine.size && engine.size.height))) || 512;
    }
    if (!isFinite(w) || w <= 0) w = 512;
    if (!isFinite(h) || h <= 0) h = 512;
    return { width: Math.round(w), height: Math.round(h) };
  }

  function makeCanvas(width, height) {
    if (typeof document !== "undefined" && document.createElement) {
      var c = document.createElement("canvas");
      c.width = width;
      c.height = height;
      return c;
    }
    // Non-DOM environment (e.g. node --check): return a minimal stub so
    // state ops stay testable without a browser.
    return {
      width: width,
      height: height,
      _stub: true,
      getContext: function () { return null; },
    };
  }

  function copyCanvas(src, width, height) {
    var dst = makeCanvas(src && src.width ? src.width : width, src && src.height ? src.height : height);
    try {
      if (src && src.getContext && dst.getContext && !dst._stub) {
        var sctx = src.getContext("2d");
        var dctx = dst.getContext("2d");
        if (sctx && dctx) dctx.drawImage(src, 0, 0);
      }
    } catch (_e) { /* best effort */ }
    return dst;
  }

  function drawOver(dst, src) {
    if (!dst || !src || dst._stub) return false;
    try {
      var dctx = dst.getContext("2d");
      if (!dctx) return false;
      var prevAlpha = dctx.globalAlpha;
      dctx.globalAlpha = 1;
      dctx.drawImage(src, 0, 0, dst.width, dst.height);
      dctx.globalAlpha = prevAlpha;
      return true;
    } catch (_e) {
      return false;
    }
  }

  /**
   * createLayerStore(engine, opts) -> store
   * opts: { width, height, baseCanvas, baseName, onSnapshot }
   */
  function createLayerStore(engine, opts) {
    var eng = engine || {};
    var options = opts || {};
    var size = resolveSize(eng, options);
    var listeners = [];
    var layers = [];
    var activeId = null;
    var suppressEngineEcho = false;

    function baseCanvas() {
      if (options.baseCanvas) return options.baseCanvas;
      if (typeof eng.getBaseCanvas === "function") {
        try {
          var bc = eng.getBaseCanvas();
          if (bc) return bc;
        } catch (_e) { /* ignore */ }
      }
      return makeCanvas(size.width, size.height);
    }

    function baseLayer() {
      return layers.length ? layers[0] : null;
    }

    function findIndex(id) {
      for (var i = 0; i < layers.length; i++) {
        if (layers[i].id === id) return i;
      }
      return -1;
    }

    function find(id) {
      var i = findIndex(id);
      return i >= 0 ? layers[i] : null;
    }

    function emit() {
      var snap = snapshot();
      for (var i = 0; i < listeners.length; i++) {
        try { listeners[i](snap); } catch (_e) { /* listener must not break store */ }
      }
    }

    function engineRender() {
      if (typeof eng.renderLayers === "function") {
        try { eng.renderLayers(); } catch (_e) { /* defensive */ }
      }
    }

    function engineSnapshot() {
      try {
        if (typeof options.onSnapshot === "function") {
          options.onSnapshot(snapshot());
          return;
        }
        var fns = ["saveToHistory", "snapshot", "pushHistory", "saveSnapshot", "historyPush", "commitHistory"];
        for (var i = 0; i < fns.length; i++) {
          if (typeof eng[fns[i]] === "function") {
            eng[fns[i]]();
            return;
          }
        }
      } catch (_e) { /* history is best-effort */ }
    }

    function commit() {
      engineRender();
      engineSnapshot();
      emit();
    }

    // Store drives engine hooks only; canvases are shared references with
    // the engine's authoritative list (base locked at index 0 inside the
    // engine). No parallel composite is kept here.
    function engineAdd(layer) {
      if (typeof eng.addLayerCanvas !== "function" || !layer) return;
      try {
        try { if (layer.canvas && layer.canvas.dataset) layer.canvas.dataset.layerId = layer.id; } catch (_e0) {}
        var r = eng.addLayerCanvas(layer.name, layer.canvas);
        var rc = r && r.canvas ? r.canvas : null;
        if (rc && rc !== layer.canvas) {
          layer.canvas = rc;
          try { if (rc.dataset) rc.dataset.layerId = layer.id; } catch (_e1) {}
        }
      } catch (_e) { /* defensive */ }
    }

    function engineSetActive(layerOrId) {
      if (typeof eng.setActiveLayer !== "function") return;
      try {
        var ref = layerOrId && layerOrId.id ? layerOrId.id : layerOrId;
        try { eng.setActiveLayer(ref); return; } catch (_e0) {}
        var l = typeof ref === "string" ? find(ref) : layerOrId;
        if (l && l.canvas) { try { eng.setActiveLayer(l.canvas); } catch (_e1) {} }
      } catch (_e) { /* defensive */ }
    }

    function engineSetVisibility(layer) {
      try {
        if (typeof eng.setLayerVisibility === "function") eng.setLayerVisibility(layer.id, layer.visible);
      } catch (_e) { /* defensive */ }
    }

    function engineSetOpacity(layer) {
      try {
        if (typeof eng.setLayerOpacity === "function") eng.setLayerOpacity(layer.id, layer.opacity);
      } catch (_e) { /* defensive */ }
    }

    // Propagate store order (bottom->top) into engine state.layers so
    // flattened output order matches the panel.
    function engineSyncOrder() {
      try {
        if (typeof eng.setLayerOrder === "function") {
          eng.setLayerOrder(layers.map(function (l) { return l.id; }));
        }
      } catch (_e) { /* defensive */ }
    }

    function engineRemove(layer) {
      if (typeof eng.removeLayerCanvas !== "function") return;
      try {
        try {
          eng.removeLayerCanvas(layer.id);
          return;
        } catch (_e) { /* fall through to canvas form */ }
        eng.removeLayerCanvas(layer.canvas);
      } catch (_e) { /* defensive */ }
    }

    function applyEngineRecordMeta(target, rec) {
      if (!target || !rec || typeof rec !== "object" || rec.id !== target.id) return;
      try {
        if (rec.name != null) target.name = String(rec.name);
        if (rec.visible != null) target.visible = !!rec.visible;
        if (rec.opacity != null && isFinite(Number(rec.opacity))) target.opacity = clamp01(rec.opacity);
        if (rec.locked != null && target.id !== BASE_ID) target.locked = !!rec.locked;
      } catch (_e) { /* metadata is best-effort */ }
    }

    function readEngineActiveRecord() {
      if (typeof eng.getActiveLayer !== "function") return null;
      try {
        var rec = eng.getActiveLayer();
        if (rec && typeof rec === "object" && rec.id) return rec;
      } catch (_e) { /* optional hook */ }
      return null;
    }

    // Re-adopt the engine's live layer canvases after an engine-side
    // restore (undo/redo): match by id, update shared references in place,
    // drop records the engine no longer has, adopt restored ones, then
    // reconcile the active selection. Best-effort and fully guarded —
    // no-ops when the engine exposes no layer list.
    function reconcileFromEngine() {
      if (typeof eng.getLayerCanvases !== "function") return false;
      var live = null;
      try { live = eng.getLayerCanvases(); } catch (_e) { return false; }
      if (!live || !live.length) return false;
      var byId = {};
      var order = [];
      for (var i = 0; i < live.length; i++) {
        var c = live[i];
        if (!c) continue;
        var cid = null;
        try { cid = c.dataset && c.dataset.layerId ? c.dataset.layerId : null; } catch (_e0) { cid = null; }
        if (!cid && i === 0) cid = BASE_ID; // engine base always leads
        if (!cid || byId[cid]) continue;
        byId[cid] = c;
        order.push(cid);
      }
      if (!order.length) return false;
      var activeRec = readEngineActiveRecord();
      var next = [];
      for (var k = 0; k < order.length; k++) {
        var id = order[k];
        var known = find(id);
        if (known) {
          known.canvas = byId[id];
          if (activeRec) applyEngineRecordMeta(known, activeRec);
          next.push(known);
        } else {
          var created = {
            id: id,
            name: id === BASE_ID ? (options.baseName || "Base") : ("Layer " + (k + 1)),
            canvas: byId[id],
            visible: true,
            opacity: 1,
            locked: id === BASE_ID,
          };
          if (activeRec) applyEngineRecordMeta(created, activeRec);
          try { if (created.canvas && created.canvas.dataset) created.canvas.dataset.layerId = id; } catch (_e1) {}
          next.push(created);
        }
      }
      layers.length = 0;
      for (var m = 0; m < next.length; m++) layers.push(next[m]);
      // Reconcile the active selection against the engine's live state.
      var activeOk = false;
      if (activeRec && find(activeRec.id)) {
        activeId = activeRec.id;
        activeOk = true;
      }
      if (!activeOk) {
        try {
          if (typeof eng.getState === "function") {
            var st = eng.getState();
            if (st && st.activeLayerIndex != null && live[st.activeLayerIndex]) {
              var ac = live[st.activeLayerIndex];
              var aid = null;
              try { aid = ac.dataset && ac.dataset.layerId ? ac.dataset.layerId : null; } catch (_e2) { aid = null; }
              if (aid && find(aid)) { activeId = aid; activeOk = true; }
            }
          }
        } catch (_e3) { /* keep current selection */ }
      }
      if (!activeOk && !find(activeId)) {
        var fb = baseLayer();
        activeId = fb ? fb.id : (next.length ? next[next.length - 1].id : null);
      }
      return true;
    }

    // Propagate a rename into any engine-side record the engine exposes.
    // The engine here offers no rename setter, so try common setter names
    // first, then mutate a live record ref when one is exposed (guarded).
    // If neither exists the engine history label goes stale (accepted).
    function engineSetName(layer) {
      if (!layer) return;
      try {
        var setters = ["setLayerName", "renameLayer", "rename", "updateLayerName", "setName"];
        for (var i = 0; i < setters.length; i++) {
          if (typeof eng[setters[i]] === "function") {
            try { eng[setters[i]](layer.id, layer.name); return; } catch (_e0) {}
          }
        }
        var rec = readEngineActiveRecord();
        // readEngineActiveRecord takes no ref — only adopt when ids match.
        if (rec && rec.id === layer.id) {
          try { rec.name = layer.name; } catch (_e1) {}
        }
      } catch (_e) { /* defensive */ }
    }

    function snapshot() {
      return {
        layers: layers.slice(),
        activeId: activeId,
      };
    }

    // ---- init: adopt the engine's authoritative base (index 0) + any
    // pre-existing engine canvases; only create a base canvas when the
    // engine has none. Canvases are shared references, not copies.
    (function init() {
      var existing = null;
      if (typeof eng.getLayerCanvases === "function") {
        try { existing = eng.getLayerCanvases(); } catch (_e) { existing = null; }
      }
      var baseC = (existing && existing.length && existing[0]) || null;
      if (!baseC) baseC = baseCanvas();
      var base = {
        id: BASE_ID,
        name: options.baseName || "Base",
        canvas: baseC,
        visible: true,
        opacity: 1,
        locked: true,
      };
      try {
        if (base.canvas && base.canvas.dataset) base.canvas.dataset.layerId = BASE_ID;
      } catch (_e) { /* stub canvas */ }
      layers.push(base);
      activeId = BASE_ID;

      if (existing && existing.length > 1) {
        for (var i = 1; i < existing.length; i++) {
          var c = existing[i];
          if (!c || c === base.canvas) continue;
          var layer = {
            id: nextId("layer"),
            name: "Layer " + layers.length,
            canvas: c,
            visible: true,
            opacity: 1,
            locked: false,
          };
          try {
            if (c.dataset) c.dataset.layerId = layer.id;
            if (c.style) c.style.opacity = "1";
          } catch (_e) { /* ignore */ }
          layers.push(layer);
          activeId = layer.id;
        }
      }

      if (typeof eng.onChange === "function") {
        try {
          eng.onChange(function () {
            if (suppressEngineEcho) return;
            // Engine-side restore (undo/redo): re-adopt live canvas
            // references by id, drop stale ones, reconcile selection,
            // re-render — then emit the reconciled snapshot.
            reconcileFromEngine();
            engineRender();
            emit();
          });
        } catch (_e) { /* optional hook */ }
      }
    })();

    var store = {
      BASE_ID: BASE_ID,

      get layers() { return layers.slice(); },
      get activeId() { return activeId; },

      get(id) { return find(id) || null; },

      getActive() { return find(activeId) || baseLayer(); },

      setActive(id) {
        var l = find(id);
        if (!l) return false;
        activeId = l.id;
        engineSetActive(l);
        engineRender();
        emit();
        return true;
      },

      add: function (name) {
        var canvas = makeCanvas(size.width, size.height);
        var layer = {
          id: nextId("layer"),
          name: String(name || ("Layer " + layers.length)),
          canvas: canvas,
          visible: true,
          opacity: 1,
          locked: false,
        };
        try {
          if (canvas.dataset) canvas.dataset.layerId = layer.id;
        } catch (_e) { /* stub */ }
        layers.push(layer);
        activeId = layer.id;
        suppressEngineEcho = true;
        try { engineAdd(layer); engineSetActive(layer); } finally { suppressEngineEcho = false; }
        commit();
        return layer;
      },

      delete: function (id) {
        var idx = findIndex(id);
        if (idx < 0) return false;
        if (isBase(layers[idx])) return false; // base protection
        var removed = layers.splice(idx, 1)[0];
        suppressEngineEcho = true;
        try { engineRemove(removed); } finally { suppressEngineEcho = false; }
        if (activeId === id) {
          var fallback = layers[Math.min(idx, layers.length - 1)];
          activeId = fallback ? fallback.id : null;
          if (fallback) engineSetActive(fallback);
        }
        commit();
        return true;
      },

      rename: function (id, name) {
        var l = find(id);
        if (!l) return false;
        var next = String(name == null ? "" : name).trim().slice(0, 80);
        if (!next) return false;
        l.name = next;
        engineSetName(l);
        commit();
        return true;
      },

      toggleVisibility: function (id) {
        var l = find(id);
        if (!l) return false;
        l.visible = !l.visible;
        engineSetVisibility(l);
        commit();
        return l.visible;
      },

      setVisibility: function (id, visible) {
        var l = find(id);
        if (!l) return false;
        l.visible = !!visible;
        engineSetVisibility(l);
        commit();
        return l.visible;
      },

      setOpacity: function (id, value) {
        var l = find(id);
        if (!l) return false;
        l.opacity = clamp01(value);
        engineSetOpacity(l);
        commit();
        return l.opacity;
      },

      /**
       * reorder(id, dir) — dir: "up" | "down" | +1 | -1.
       * Base stays at index 0; nothing may move below it.
       */
      reorder: function (id, dir) {
        var idx = findIndex(id);
        if (idx < 0) return false;
        if (isBase(layers[idx])) return false; // base is locked at bottom
        var delta = dir === "up" || dir === 1 || dir === "+1" ? 1
          : dir === "down" || dir === -1 || dir === "-1" ? -1 : 0;
        if (!delta) return false;
        var target = idx + delta;
        if (target < 1) return false; // cannot go below/at base
        if (target >= layers.length) return false;
        var tmp = layers[idx];
        layers[idx] = layers[target];
        layers[target] = tmp;
        engineSyncOrder();
        commit();
        return true;
      },

      moveTo: function (id, index) {
        var idx = findIndex(id);
        if (idx < 0) return false;
        if (isBase(layers[idx])) return false;
        var target = Math.max(1, Math.min(layers.length - 1, Math.floor(Number(index))));
        if (!isFinite(target) || target === idx) return false;
        var item = layers.splice(idx, 1)[0];
        layers.splice(target, 0, item);
        engineSyncOrder();
        commit();
        return true;
      },

      duplicate: function (id) {
        var idx = findIndex(id || activeId);
        if (idx < 0) return null;
        var src = layers[idx];
        var canvas = copyCanvas(src.canvas, size.width, size.height);
        var layer = {
          id: nextId("layer"),
          name: (src.name || "Layer") + " copy",
          canvas: canvas,
          visible: src.visible !== false,
          opacity: clamp01(src.opacity == null ? 1 : src.opacity),
          locked: false,
        };
        try {
          if (canvas.dataset) canvas.dataset.layerId = layer.id;
        } catch (_e) { /* stub */ }
        layers.splice(idx + 1, 0, layer);
        activeId = layer.id;
        suppressEngineEcho = true;
        try { engineAdd(layer); engineSetVisibility(layer); engineSetOpacity(layer); engineSyncOrder(); engineSetActive(layer); } finally { suppressEngineEcho = false; }
        commit();
        return layer;
      },

      /**
       * mergeDown(id) — composite layer onto the layer directly below it,
       * then remove the merged layer. Merging onto base keeps base.
       */
      mergeDown: function (id) {
        var idx = findIndex(id || activeId);
        if (idx <= 0) return false; // base (index 0) has nothing below
        var top = layers[idx];
        if (isBase(top)) return false;
        var below = layers[idx - 1];
        // Respect visibility/opacity: a hidden top layer contributes
        // nothing (drop it); otherwise composite at its own opacity.
        if (top.visible !== false) {
          var alpha = clamp01(top.opacity == null ? 1 : top.opacity);
          if (alpha > 0) {
            try {
              if (!below.canvas._stub && top.canvas && alpha < 1) {
                var mctx = below.canvas.getContext("2d");
                if (mctx) {
                  var prev = mctx.globalAlpha;
                  mctx.globalAlpha = alpha;
                  mctx.drawImage(top.canvas, 0, 0, below.canvas.width, below.canvas.height);
                  mctx.globalAlpha = prev;
                } else {
                  drawOver(below.canvas, top.canvas);
                }
              } else {
                drawOver(below.canvas, top.canvas);
              }
            } catch (_e) { /* best effort */ }
          }
        }
        layers.splice(idx, 1);
        suppressEngineEcho = true;
        try { engineRemove(top); } finally { suppressEngineEcho = false; }
        activeId = below.id;
        engineSetActive(below);
        commit();
        return true;
      },

      /**
       * flatten() — composite all visible non-base layers onto base
       * (bottom-up), then remove them. Base always survives.
       */
      flatten: function () {
        var base = baseLayer();
        if (!base || layers.length <= 1) return false;
        var removed = [];
        for (var i = 1; i < layers.length; i++) {
          var l = layers[i];
          if (l.visible === false) continue;
          // Respect per-layer opacity for the composite.
          try {
            if (!base.canvas._stub && l.canvas && l.opacity != null && l.opacity < 1) {
              var ctx = base.canvas.getContext("2d");
              if (ctx) {
                var prev = ctx.globalAlpha;
                ctx.globalAlpha = clamp01(l.opacity);
                ctx.drawImage(l.canvas, 0, 0, base.canvas.width, base.canvas.height);
                ctx.globalAlpha = prev;
              } else {
                drawOver(base.canvas, l.canvas);
              }
            } else {
              drawOver(base.canvas, l.canvas);
            }
          } catch (_e) { /* best effort */ }
          removed.push(l);
        }
        // Drop every non-base layer (hidden ones too — a flatten collapses all).
        var dropped = layers.splice(1);
        suppressEngineEcho = true;
        try {
          for (var j = 0; j < dropped.length; j++) engineRemove(dropped[j]);
        } finally { suppressEngineEcho = false; }
        activeId = base.id;
        engineSetActive(base);
        commit();
        return true;
      },

      /**
       * clearLayers — remove all non-base overlays (base survives, stays
       * locked at index 0). Snapshots history and re-renders via commit().
       * clear/reset are shell-compatible aliases (shell tries these names
       * in order: clearLayers, clear, reset).
       */
      clearLayers: function () {
        if (layers.length <= 1) return false;
        var dropped = layers.splice(1);
        suppressEngineEcho = true;
        try {
          for (var i = 0; i < dropped.length; i++) engineRemove(dropped[i]);
        } finally { suppressEngineEcho = false; }
        var base = baseLayer();
        activeId = base ? base.id : null;
        if (base) engineSetActive(base);
        commit();
        return true;
      },

      clear: function () { return store.clearLayers(); },

      reset: function () { return store.clearLayers(); },

      /**
       * undo/redo — delegate to the engine first (its history owns pixel
       * state), then re-adopt live canvases. Async restores reconcile via
       * the onChange listener — no polling.
       */
      undo: function () {
        var ok = false;
        try {
          if (typeof eng.undo === "function") ok = eng.undo() === true;
        } catch (_e) { ok = false; }
        reconcileFromEngine();
        engineRender();
        emit();
        return ok;
      },

      redo: function () {
        var ok = false;
        try {
          if (typeof eng.redo === "function") ok = eng.redo() === true;
        } catch (_e) { ok = false; }
        reconcileFromEngine();
        engineRender();
        emit();
        return ok;
      },

      subscribe: function (cb) {
        if (typeof cb !== "function") return function () {};
        listeners.push(cb);
        return function unsubscribe() {
          var i = listeners.indexOf(cb);
          if (i >= 0) listeners.splice(i, 1);
        };
      },

      /**
       * renderInto(container) — minimal sidebar panel. Re-renders the list
       * on every store change. No floating/draggable behavior.
       */
      renderInto: function (container) {
      if (!container || typeof document === "undefined") return null;
      if (!document.getElementById("sketch-layers-style")) {
        var css = document.createElement("style"); css.id = "sketch-layers-style"; css.textContent = '.sketch-layers-panel{background:rgba(249,249,249,.95);border:1px solid #ccc;border-radius:6px;box-shadow:0 2px 10px rgba(0,0,0,.15);padding:8px;color:#222;font:10px/1.3 system-ui,sans-serif}.sketch-layers-head{display:flex;align-items:center;gap:5px;padding:2px 2px 7px;border-bottom:1px solid #ccc;margin-bottom:6px}.sketch-layers-title{font-size:11px;font-weight:600;flex:1}.sketch-layers-btn{background:#e8e8e8;border:1px solid #ccc;border-radius:4px;color:#444;cursor:pointer;font:10px system-ui;min-width:24px;min-height:24px}.sketch-layers-add{display:inline-flex;align-items:center;gap:3px}.sketch-layers-add:before{content:"";display:block;width:12px;height:12px;background:currentColor;mask:url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 24 24\'%3E%3Cpath d=\'M12 5v14M5 12h14\' stroke=\'black\' stroke-width=\'2\'/%3E%3C/svg%3E") center/contain no-repeat}.sketch-layers-list{display:flex;flex-direction:column;gap:4px}.sketch-layers-row{display:grid;grid-template-columns:22px minmax(0,1fr) 48px auto;align-items:center;gap:4px;padding:5px 3px;border:1px solid transparent;border-radius:4px}.sketch-layers-row.is-active{background:#dbeeff;border-color:#b8d8f2}.sketch-layers-row.is-base{background:#f1f1f1}.sketch-layers-eye,.sketch-layers-tools button{border:0;background:transparent;color:#555;padding:3px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}.sketch-layers-eye .sketch-icon,.sketch-layers-tools .sketch-icon{width:13px;height:13px}.sketch-layers-name{min-width:0;overflow:hidden}.sketch-layers-name-text{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:text}.sketch-layers-opacity{width:48px;height:3px;appearance:none;background:#ccc;border-radius:2px}.sketch-layers-opacity::-webkit-slider-thumb{appearance:none;width:8px;height:8px;border-radius:50%;background:#555}.sketch-layers-tools{display:flex;gap:0}.sketch-layers-delete{color:#a33!important}.sketch-layers-lock{display:inline-flex;color:#666;padding:3px}.sketch-layers-panel button:focus-visible,.sketch-layers-panel input:focus-visible{outline:2px solid #4285c5;outline-offset:1px}'; (document.head || document.documentElement).appendChild(css);
      }
        var root = document.createElement("div");
        root.className = "sketch-layers-panel";
        root.setAttribute("data-sketch-layers", "1");
        container.appendChild(root);

        function el(tag, cls, text) {
          var n = document.createElement(tag);
          if (cls) n.className = cls;
          if (text != null) n.textContent = text;
          return n;
        }

        function btn(label, title, onClick) {
          var b = el("button", "sketch-layers-btn", label);
          b.type = "button";
          b.title = title || label;
          b.addEventListener("click", function (ev) {
            ev.stopPropagation();
            onClick();
          });
          return b;
        }

        function paint() {
          while (root.firstChild) root.removeChild(root.firstChild);

          var head = el("div", "sketch-layers-head");
          head.appendChild(el("span", "sketch-layers-title", "Layers"));
          var addBtn = btn("+ Add", "Add layer", function () { store.add(); });
          addBtn.classList.add("sketch-layers-add");
          head.appendChild(addBtn);
          var flatBtn = btn("Flatten", "Merge all layers onto base", function () { store.flatten(); });
          flatBtn.classList.add("sketch-layers-flatten");
          head.appendChild(flatBtn);
          root.appendChild(head);

          var list = el("div", "sketch-layers-list");
          // Top-most layer first in the UI.
          for (var i = layers.length - 1; i >= 0; i--) {
            (function (layer, index) {
              var row = el("div", "sketch-layers-row" + (layer.id === activeId ? " is-active" : "") + (isBase(layer) ? " is-base" : ""));
              row.setAttribute("data-layer-id", layer.id);
              row.addEventListener("click", function () { store.setActive(layer.id); });

              var eye = btn("", "Toggle visibility", function () {
                eye.innerHTML = icon(layer.visible === false ? "hidden" : "eye");
                store.toggleVisibility(layer.id);
              });
              eye.innerHTML = icon(layer.visible === false ? "hidden" : "eye");
              eye.classList.add("sketch-layers-eye");
              eye.setAttribute("aria-pressed", layer.visible === false ? "false" : "true");
              row.appendChild(eye);

              var nameWrap = el("div", "sketch-layers-name");
              var name = el("span", "sketch-layers-name-text", layer.name + (isBase(layer) ? " (base)" : ""));
              name.title = isBase(layer) ? "Base image — locked, cannot delete" : "Double-click to rename";
              nameWrap.appendChild(name);
              nameWrap.addEventListener("dblclick", function () {
                if (typeof window !== "undefined" && typeof window.prompt === "function") {
                  var next = window.prompt("Rename layer", layer.name);
                  if (next != null) store.rename(layer.id, next);
                }
              });
              row.appendChild(nameWrap);

              var slider = document.createElement("input");
              slider.type = "range";
              slider.min = "0";
              slider.max = "1";
              slider.step = "0.01";
              slider.value = String(clamp01(layer.opacity == null ? 1 : layer.opacity));
              slider.title = "Opacity";
              slider.className = "sketch-layers-opacity";
              slider.addEventListener("click", function (ev) { ev.stopPropagation(); });
              slider.addEventListener("input", function () {
                store.setOpacity(layer.id, Number(slider.value));
              });
              // Avoid full re-render steal while dragging the slider: the
              // store emits on input; paint() rebuilds rows which would drop
              // the drag. Update only the engine + snapshot path by siding
              // through setOpacity (needed for history), acceptable here.
              row.appendChild(slider);

              var tools = el("div", "sketch-layers-tools");
              if (!isBase(layer)) {
                 var up = btn("", "Move up", function () { store.reorder(layer.id, "up"); }); up.innerHTML = icon("up"); tools.appendChild(up);
                 var down = btn("", "Move down", function () { store.reorder(layer.id, "down"); }); down.innerHTML = icon("down"); tools.appendChild(down);
                 var dup = btn("", "Duplicate", function () { store.duplicate(layer.id); }); dup.innerHTML = icon("duplicate"); tools.appendChild(dup);
                 var merge = btn("", "Merge down", function () { store.mergeDown(layer.id); }); merge.innerHTML = icon("merge"); tools.appendChild(merge);
                 var del = btn("", "Delete layer", function () { store.delete(layer.id); }); del.innerHTML = icon("delete");
                del.classList.add("sketch-layers-delete");
                tools.appendChild(del);
              } else {
                 var lock = el("span", "sketch-layers-lock"); lock.innerHTML = icon("lock");
                lock.title = "Base is locked at the bottom";
                tools.appendChild(lock);
              }
              row.appendChild(tools);
              list.appendChild(row);
            })(layers[i], i);
          }
          root.appendChild(list);
        }

        var off = store.subscribe(paint);
        paint();
        root._destroyLayersPanel = function () {
          try { off(); } catch (_e) { /* ignore */ }
          if (root.parentNode) root.parentNode.removeChild(root);
        };
        return root;
      },
    };

    return store;
  }

  var api = { createLayerStore: createLayerStore, BASE_ID: BASE_ID };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  global.ComfyModalSketchLayers = api;
  if (typeof window !== "undefined") window.ComfyModalSketchLayers = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
