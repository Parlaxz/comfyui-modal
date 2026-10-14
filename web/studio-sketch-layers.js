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

    // Unique display names. Defaults follow "Layer 1, Layer 2, ..." using
    // the lowest unused number. Every live name counts (base row,
    // overlays, renames, restored records) so a live name is never reused.
    function isNameTaken(name, extra) {
      var s = String(name);
      for (var i = 0; i < layers.length; i++) {
        if (layers[i] && String(layers[i].name) === s) return true;
      }
      if (extra) {
        for (var j = 0; j < extra.length; j++) {
          if (extra[j] && String(extra[j].name) === s) return true;
        }
      }
      return false;
    }

    function nextDefaultLayerName(extra) {
      var n = 1;
      while (isNameTaken("Layer " + n, extra)) n++;
      return "Layer " + n;
    }

    function uniqueNameFor(candidate, extra) {
      var nm = String(candidate == null ? "" : candidate).trim();
      if (nm && !isNameTaken(nm, extra)) return nm;
      return nextDefaultLayerName(extra);
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
            name: id === BASE_ID ? (options.baseName || "Base") : nextDefaultLayerName(next),
            canvas: byId[id],
            visible: true,
            opacity: 1,
            locked: id === BASE_ID,
          };
          if (activeRec) applyEngineRecordMeta(created, activeRec);
          if (id !== BASE_ID) created.name = uniqueNameFor(created.name, next);
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
          var hint = "";
          try { hint = c && c.dataset && c.dataset.layerName ? String(c.dataset.layerName).trim() : ""; } catch (_e0) { hint = ""; }
          var layer = {
            id: nextId("layer"),
            name: uniqueNameFor(hint, null),
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
          name: name ? String(name) : nextDefaultLayerName(),
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
        var copyStem = (src.name || "Layer") + " copy";
        var copyName = copyStem;
        var copyN = 2;
        while (isNameTaken(copyName)) { copyName = copyStem + " " + copyN; copyN++; }
        var layer = {
          id: nextId("layer"),
          name: copyName,
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
       * renderInto(container) — compact sidebar panel for the ~333px LEFT
       * Studio sidebar. Single-column rows (eye | name | opacity | tools),
       * internal list scroll (max-height ~220px) so header actions never
       * get pushed away. Native dark Studio styling.
       */
      renderInto: function (container) {
        if (!container || typeof document === "undefined") return null;
        if (!document.getElementById("sketch-layers-style")) {
          var css = document.createElement("style");
          css.id = "sketch-layers-style";
          css.textContent = [
            ".sketch-layers-panel{background:#202024;border:1px solid #33333a;border-radius:6px;box-sizing:border-box;width:100%;max-width:100%;padding:6px;color:#c9c9d1;font:10px/1.3 system-ui,sans-serif}",
            ".sketch-layers-head{display:flex;align-items:center;gap:4px;padding:2px 2px 6px;border-bottom:1px solid #33333a;margin-bottom:5px}",
            ".sketch-layers-title{font-size:11px;font-weight:600;flex:1;min-width:0;color:#e4e4ea}",
            ".sketch-layers-btn{background:#2a2a31;border:1px solid #3d3d46;border-radius:4px;color:#c9c9d1;cursor:pointer;font:10px system-ui,sans-serif;padding:2px 6px;min-height:20px;line-height:1.2;white-space:nowrap}",
            ".sketch-layers-btn:hover{background:#34343d}",
            ".sketch-layers-add,.sketch-layers-flatten{flex:none}",
            ".sketch-layers-list{display:flex;flex-direction:column;gap:2px;max-height:220px;overflow-y:auto;overflow-x:hidden;padding-right:2px}",
            ".sketch-layers-row{display:grid;grid-template-columns:18px minmax(0,1fr) 44px auto;align-items:center;gap:3px;min-height:24px;padding:1px 2px;border:1px solid transparent;border-radius:4px;box-sizing:border-box}",
            ".sketch-layers-row:hover{background:rgba(255,255,255,.04)}",
            ".sketch-layers-row.is-active{background:#2c3d52;border-color:#4a6a94}",
            ".sketch-layers-row.is-base{background:rgba(255,255,255,.03)}",
            ".sketch-layers-eye,.sketch-layers-tools button{border:0;background:transparent;color:#9a9aa3;padding:1px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;min-width:18px;border-radius:3px}",
            ".sketch-layers-eye:hover,.sketch-layers-tools button:hover{color:#e4e4ea;background:rgba(255,255,255,.08)}",
            ".sketch-layers-eye .sketch-icon,.sketch-layers-tools .sketch-icon{width:12px;height:12px}",
            ".sketch-icon{width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}",
            ".sketch-layers-name{min-width:0;overflow:hidden}",
            ".sketch-layers-name-text{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:text;font-size:10px}",
            ".sketch-layers-opacity{width:44px;height:3px;appearance:none;-webkit-appearance:none;background:#3d3d46;border-radius:2px;outline:none;padding:0;margin:0}",
            ".sketch-layers-opacity::-webkit-slider-thumb{appearance:none;-webkit-appearance:none;width:8px;height:8px;border-radius:50%;background:#c9c9d1;cursor:pointer;border:0}",
            ".sketch-layers-opacity::-moz-range-thumb{width:8px;height:8px;border-radius:50%;background:#c9c9d1;cursor:pointer;border:0}",
            ".sketch-layers-tools{display:inline-flex;align-items:center;gap:0;flex:none}",
            ".sketch-layers-lock{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;color:#6a6a73}",
            ".sketch-layers-lock .sketch-icon{width:12px;height:12px}",
            ".sketch-layers-name-text{background:transparent;border:0;color:inherit;font-size:10px;text-align:left;padding:0;margin:0;width:100%;cursor:pointer}",
            ".sketch-layers-name-text:hover{color:#fff}",
            ".sketch-layers-btn:disabled,.sketch-layers-eye:disabled{opacity:.35;cursor:default}",
            ".sketch-layers-name-text:focus-visible,.sketch-layers-btn:focus-visible,.sketch-layers-eye:focus-visible,.sketch-layers-opacity:focus-visible{outline:1px solid #6a9fd8;outline-offset:1px}",
            ".sketch-layers-rename{font-size:9px;padding:2px 4px}"
          ].join("");
        }
        var root = document.createElement("div");
        root.className = "sketch-layers-panel";
        root.setAttribute("data-sketch-layers", "1");
        root.setAttribute("data-testid", "sketch-layers-panel");
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

        // Shared rename flow (prompt mechanism): used by the per-row Rename
        // button (keyboard-accessible) and the name dblclick pointer
        // affordance. No inline editor — the prompt stays canonical.
        function promptRename(layerId) {
          var target = find(layerId);
          if (!target) return;
          if (typeof window !== "undefined" && typeof window.prompt === "function") {
            var next = window.prompt("Rename layer", target.name);
            if (next != null) store.rename(target.id, next);
          }
        }

        // Persistent panel nodes: head + list are built once and rows are
        // keyed by layer id and updated in place, so store emits (opacity
        // drags, selection changes) never rebuild row/input nodes, never
        // move focus, and never reset list scroll.
        var list = null;
        var flatBtn = null;
        var rowById = {};

        function buildRow(layerId) {
          var row = el("div", "sketch-layers-row");
          row.setAttribute("data-layer-id", layerId);
          row.setAttribute("data-testid", "sketch-layers-row");
          row.setAttribute("data-active", "false");
          row.addEventListener("click", function () { store.setActive(layerId); });

          var eye = btn("", "Toggle visibility", function () { store.toggleVisibility(layerId); });
          eye.classList.add("sketch-layers-eye");
          eye.setAttribute("data-testid", "sketch-layers-eye");
          row.appendChild(eye);

          var nameWrap = el("div", "sketch-layers-name");
          var nameBtn = el("button", "sketch-layers-name-text");
          nameBtn.type = "button";
          nameBtn.setAttribute("data-testid", "sketch-layers-name");
          nameBtn.addEventListener("click", function (ev) {
            ev.stopPropagation();
            store.setActive(layerId);
          });
          nameWrap.appendChild(nameBtn);
          nameWrap.addEventListener("dblclick", function () { promptRename(layerId); });
          row.appendChild(nameWrap);

          var slider = document.createElement("input");
          slider.type = "range";
          slider.min = "0";
          slider.max = "1";
          slider.step = "0.01";
          slider.className = "sketch-layers-opacity";
          slider.setAttribute("data-testid", "sketch-layers-opacity");
          slider.addEventListener("click", function (ev) { ev.stopPropagation(); });
          slider.addEventListener("input", function () {
            store.setOpacity(layerId, Number(slider.value));
          });
          row.appendChild(slider);

          var tools = el("div", "sketch-layers-tools");
          tools.setAttribute("data-testid", "sketch-layers-tools");
          function toolBtn(testid, glyph, label, fn, extraCls) {
            var b = btn("", label, fn);
            b.innerHTML = glyph;
            b.setAttribute("data-testid", testid);
            if (extraCls) b.classList.add(extraCls);
            tools.appendChild(b);
            return b;
          }
          var up = toolBtn("sketch-layers-up", icon("up"), "Move up", function () { store.reorder(layerId, "up"); });
          var down = toolBtn("sketch-layers-down", icon("down"), "Move down", function () { store.reorder(layerId, "down"); });
          var dup = toolBtn("sketch-layers-dup", icon("duplicate"), "Duplicate", function () { store.duplicate(layerId); });
          var merge = toolBtn("sketch-layers-merge", icon("merge"), "Merge down", function () { store.mergeDown(layerId); });
          var del = toolBtn("sketch-layers-delete", icon("delete"), "Delete layer", function () { store.delete(layerId); }, "sketch-layers-delete");
          var renameBtn = el("button", "sketch-layers-btn sketch-layers-rename");
          renameBtn.type = "button";
          renameBtn.textContent = "Rename";
          renameBtn.setAttribute("data-testid", "sketch-layers-rename");
          renameBtn.addEventListener("click", function (ev) {
            ev.stopPropagation();
            promptRename(layerId);
          });
          tools.appendChild(renameBtn);
          var lock = el("span", "sketch-layers-lock");
          lock.innerHTML = icon("lock");
          lock.title = "Base is locked at the bottom";
          lock.setAttribute("data-testid", "sketch-layers-lock");
          row.appendChild(tools);
          return {
            row: row, eye: eye, _eyeKey: null, nameBtn: nameBtn,
            slider: slider, tools: tools, up: up, down: down, dup: dup,
            merge: merge, del: del, renameBtn: renameBtn, lock: lock,
          };
        }

        function updateRow(state, layer, idx, total) {
          var nm = layer.name != null ? String(layer.name) : "layer";
          var base = isBase(layer);
          var isActive = layer.id === activeId;
          state.row.className = "sketch-layers-row" + (isActive ? " is-active" : "") + (base ? " is-base" : "");
          state.row.setAttribute("data-active", isActive ? "true" : "false");

          // Eye (kept separate from the tools group): icon swaps only on
          // visibility flips so the button node (and focus) is stable.
          var vis = layer.visible !== false;
          var eyeKey = vis ? "eye" : "hidden";
          if (state._eyeKey !== eyeKey) {
            state.eye.innerHTML = icon(eyeKey);
            state._eyeKey = eyeKey;
          }
          var eyeLabel = (vis ? "Hide " : "Show ") + nm;
          state.eye.setAttribute("aria-pressed", vis ? "true" : "false");
          state.eye.setAttribute("aria-label", eyeLabel);
          state.eye.title = eyeLabel;

          // Name: real focusable control with button semantics — click (or
          // Enter/Space) selects; selection announced via aria-pressed.
          var nameLabel = nm + (base ? " (base)" : "");
          if (state.nameBtn.textContent !== nameLabel) state.nameBtn.textContent = nameLabel;
          state.nameBtn.setAttribute("aria-pressed", isActive ? "true" : "false");
          state.nameBtn.setAttribute("aria-label", "Select " + nm);
          state.nameBtn.title = base ? "Base image — locked, cannot delete" : "Select " + nm + " — double-click to rename";

          // Opacity: never rewrite the value of the slider being dragged —
          // the store echo of our own input event must not disturb the drag
          // (or steal focus); update it once the drag moves elsewhere.
          var targetVal = String(clamp01(layer.opacity == null ? 1 : layer.opacity));
          try {
            if (typeof document === "undefined" || document.activeElement !== state.slider) {
              if (state.slider.value !== targetVal) state.slider.value = targetVal;
            }
          } catch (_e) {
            try { state.slider.value = targetVal; } catch (_e2) { /* ignore */ }
          }
          var opLabel = "Opacity for " + nm;
          state.slider.setAttribute("aria-label", opLabel);
          state.slider.title = opLabel;

          // Base shows the lock instead of the move/duplicate/merge/delete
          // set; the Rename button stays for every row.
          var actionBtns = [state.up, state.down, state.dup, state.merge, state.del];
          for (var k = 0; k < actionBtns.length; k++) {
            actionBtns[k].style.display = base ? "none" : "";
          }
          if (base) {
            if (!state.lock.parentNode || state.lock.parentNode !== state.tools) state.tools.appendChild(state.lock);
          } else if (state.lock.parentNode === state.tools) {
            state.tools.removeChild(state.lock);
          }

          // Layer-specific accessible names + impossible actions disabled.
          var upLabel = "Move up " + nm;
          state.up.setAttribute("aria-label", upLabel);
          state.up.title = upLabel;
          state.up.disabled = base || idx >= total - 1; // top already
          var downLabel = "Move down " + nm;
          state.down.setAttribute("aria-label", downLabel);
          state.down.title = downLabel;
          state.down.disabled = base || idx <= 1; // above base: below is base
          var dupLabel = "Duplicate " + nm;
          state.dup.setAttribute("aria-label", dupLabel);
          state.dup.title = dupLabel;
          state.dup.disabled = !!base;
          var mergeLabel = "Merge down " + nm;
          state.merge.setAttribute("aria-label", mergeLabel);
          state.merge.title = mergeLabel;
          state.merge.disabled = base || idx <= 0; // base has nothing below
          var delLabel = "Delete " + nm;
          state.del.setAttribute("aria-label", delLabel);
          state.del.title = delLabel;
          state.del.disabled = !!base;
          var renameLabel = "Rename " + nm;
          state.renameBtn.setAttribute("aria-label", renameLabel);
          state.renameBtn.title = renameLabel;
        }

        function sync() {
          if (!list) return;
          var savedTop = null;
          try { savedTop = list.scrollTop; } catch (_e) { savedTop = null; }
          var seen = {};
          for (var a = layers.length - 1; a >= 0; a--) {
            var layer = layers[a];
            seen[layer.id] = true;
            var state = rowById[layer.id] || (rowById[layer.id] = buildRow(layer.id));
            updateRow(state, layer, a, layers.length);
          }
          for (var staleId in rowById) {
            if (!seen[staleId]) {
              try {
                if (rowById[staleId].row.parentNode === list) list.removeChild(rowById[staleId].row);
              } catch (_e2) { /* ignore */ }
              delete rowById[staleId];
            }
          }
          // Re-append in UI order (top-most first); appendChild moves live
          // nodes without destroying them, so focus survives reorders.
          for (var b = layers.length - 1; b >= 0; b--) {
            list.appendChild(rowById[layers[b].id].row);
          }
          if (flatBtn) {
            var single = layers.length <= 1;
            flatBtn.disabled = single;
            flatBtn.setAttribute("aria-disabled", single ? "true" : "false");
            flatBtn.title = single ? "Nothing to flatten" : "Merge all layers onto base";
          }
          if (savedTop != null) {
            try { list.scrollTop = savedTop; } catch (_e3) { /* ignore */ }
          }
        }

        var head = el("div", "sketch-layers-head");
        head.setAttribute("data-testid", "sketch-layers-head");
        head.appendChild(el("span", "sketch-layers-title", "Layers"));
        var addBtn = btn("+ Add", "Add layer", function () { store.add(); });
        addBtn.classList.add("sketch-layers-add");
        addBtn.setAttribute("data-testid", "sketch-layers-add");
        head.appendChild(addBtn);
        flatBtn = btn("Flatten", "Merge all layers onto base", function () { store.flatten(); });
        flatBtn.classList.add("sketch-layers-flatten");
        flatBtn.setAttribute("data-testid", "sketch-layers-flatten");
        root.appendChild(head);

        list = el("div", "sketch-layers-list");
        list.setAttribute("data-testid", "sketch-layers-list");
        root.appendChild(list);

        var off = store.subscribe(sync);
        sync();
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
