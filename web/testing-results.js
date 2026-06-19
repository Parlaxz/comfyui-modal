// web/testing-results.js
//
// Results UI — Five operational zones:
//   1. Run command bar    (picker + routine controls + separated danger controls)
//   2. Run status summary (compact glanceable counters)
//   3. Checkpoint activity(active worker cards & progress bars)
//   4. Results gallery    (completed cell grid)
//   5. Comparison workspace (A/B slider workspace)
//
// Wired to /comfymodal/experiments/{id}/events and snapshot routes.

export function results_tab_render(rootEl, api, options = {}) {
  function el(tag, props = {}, children = []) {
    const e = document.createElement(tag);
    for (const k in props) {
      if (k === "class") e.className = props[k];
      else if (k === "style") e.style.cssText = props[k];
      else if (k === "text") e.textContent = props[k];
      else if (k.startsWith("on") && typeof props[k] === "function") {
        e.addEventListener(k.slice(2).toLowerCase(), props[k]);
      } else if (k === "value") {
        e.value = props[k];
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

  async function fetchJson(path, options = {}) {
    const res = await fetch(path, options);
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
    if (!res.ok) {
      const msg = (data && data.message) || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function status(text, level = "info") {
    return el("div", { class: `testing-results-status testing-results-status-${level}`, text });
  }

  // ── Zone 2: Run status summary ─────────────────────────────

  function summarySection() {
    return el("section", { class: "testing-results-summary", "data-section": "summary" }, [
      el("div", { class: "testing-results-summary-card", "data-testid": "summary-card" }, [
        el("div", { class: "testing-results-summary-primary", "data-testid": "summary-primary" }, [
          el("span", { class: "summary-stat-value completed", "data-testid": "completed", text: "0" }),
          el("span", { class: "summary-stat-label", text: "completed" }),
        ]),
        el("div", { class: "summary-stat" }, [
          el("span", { class: "summary-stat-label", text: "Failed" }),
          el("span", { class: "summary-stat-value failed", "data-testid": "failed", text: "0" }),
        ]),
        el("div", { class: "summary-stat" }, [
          el("span", { class: "summary-stat-label", text: "Skipped" }),
          el("span", { class: "summary-stat-value skipped", "data-testid": "skipped", text: "0" }),
        ]),
        el("div", { class: "summary-stat" }, [
          el("span", { class: "summary-stat-label", text: "Status" }),
          el("span", { class: "summary-stat-value", "data-testid": "status", text: "draft" }),
        ]),
      ]),
    ]);
  }

  // ── Zone 3: Checkpoint activity ────────────────────────────

  function progressSection() {
    return el("section", { class: "testing-results-progress", "data-section": "progress" }, [
      el("h3", { style: "font-size:var(--font-size-sm,12px);font-weight:var(--font-weight-semibold,600);color:var(--color-text-primary,#e1e4ea);margin:0 0 var(--space-sm,8px);", text: "Checkpoint Activity" }),
      el("div", { class: "testing-results-checkpoint-list", "data-testid": "checkpoint-list" }),
    ]);
  }

  // ── Zone 4: Results gallery ────────────────────────────────

  function gridSection() {
    return el("section", { class: "testing-results-gallery", "data-section": "grid" }, [
      el("h3", { style: "font-size:var(--font-size-sm,12px);font-weight:var(--font-weight-semibold,600);color:var(--color-text-primary,#e1e4ea);margin:0 0 var(--space-sm,8px);", text: "Results" }),
      el("div", { class: "testing-results-grid-body", "data-testid": "grid-body" }, [
        el("div", { class: "testing-results-empty-state", text: "Select an experiment above and start it. Cells appear here as they complete." }),
      ]),
    ]);
  }

  // ── Zone 5: Comparison workspace ───────────────────────────

  function comparisonSlotSection(apiBase) {
    return el("section", { class: "testing-results-compare-workspace", "data-section": "compare" }, [
      el("h3", { style: "font-size:var(--font-size-sm,12px);font-weight:var(--font-weight-semibold,600);color:var(--color-text-primary,#e1e4ea);margin:0 0 var(--space-sm,8px);", text: "Comparison" }),
      el("div", { class: "testing-results-compare-body", "data-testid": "compare-body" }, [
        el("p", { class: "testing-results-empty-state",
          text: "Right-click two images to compare them here" }),
      ]),
      el("div", { class: "testing-results-compare-actions", style: "display:flex;gap:var(--space-sm,8px);margin-top:var(--space-sm,8px);" }, [
        el("button", { class: "testing-results-btn comfymodal-secondary-btn", "data-control": "compare-fullscreen", text: "Fullscreen" }),
        el("button", { class: "testing-results-btn comfymodal-secondary-btn", "data-control": "compare-swap", text: "Swap" }),
      ]),
    ]);
  }

  // ── Control helpers ────────────────────────────────────────

  const ROUTINE_CONTROLS = ["Pause", "Resume", "Run missing"];
  const DANGER_CONTROLS = ["Stop after current", "Stop now"];

  const CONTROL_VARIANT = {
    "Pause": "testing-results-btn-pause",
    "Resume": "testing-results-btn-resume",
    "Stop after current": "testing-results-btn-stop-after",
    "Stop now": "testing-results-btn-stop-now",
    "Run missing": "testing-results-btn-run-missing",
  };

  // ── Zone 1: Command bar ────────────────────────────────────

  function commandBarSection(apiBase, experimentId) {
    return el("section", { class: "testing-results-command-bar", "data-section": "command-bar" }, [
      el("div", { class: "testing-results-command-main" }, [
        experimentPicker(apiBase, experimentId),
      ]),
      el("div", { class: "testing-results-command-routine testing-results-command-main" }, [
        ...ROUTINE_CONTROLS.map((c) => {
          const variant = CONTROL_VARIANT[c] || "";
          const b = el("button", { class: `testing-results-btn ${variant} comfymodal-secondary-btn`, "data-control": c, text: c });
          b.addEventListener("click", () => runControl(apiBase, experimentId, c, b));
          return b;
        }),
      ]),
      el("div", { class: "testing-results-command-danger" }, [
        ...DANGER_CONTROLS.map((c) => {
          const variant = CONTROL_VARIANT[c] || "";
          const b = el("button", { class: `testing-results-btn ${variant} comfymodal-destructive-btn`, "data-control": c, text: c });
          b.addEventListener("click", () => runControl(apiBase, experimentId, c, b));
          return b;
        }),
      ]),
    ]);
  }

  async function runControl(apiBase, experimentId, name, btn) {
    if (!experimentId) return;
    if (name === "Stop now" &&
        !window.confirm("Stop now kills all running cells immediately. Continue?")) {
      return;
    }
    if (name === "Stop after current" &&
        !window.confirm("Stop after current — no new cells will start, running ones finish. Continue?")) {
      return;
    }
    btn.disabled = true;
    const path = ({
      "Pause": "pause",
      "Stop after current": "stop-after-current",
      "Stop now": "stop-now",
      "Resume": "resume",
      "Run missing": "run-missing",
    })[name];
    if (!path) { btn.disabled = false; return; }
    try {
      await fetchJson(`${apiBase}/experiments/${encodeURIComponent(experimentId)}/${path}`, { method: "POST" });
    } catch (e) {
      console.error("control failed", e);
    }
    btn.disabled = false;
  }

  function experimentPicker(apiBase, currentId) {
    const wrap = el("div", { class: "testing-results-picker", style: "display:flex;align-items:center;gap:var(--space-sm,8px);" });
    const refresh = async () => {
      while (wrap.firstChild) wrap.removeChild(wrap.firstChild);
      try {
        const data = await fetchJson(`${apiBase}/experiments`);
        const exps = (data && data.experiments) || [];
        wrap.appendChild(el("label", { style: "font-size:var(--font-size-sm,12px);color:var(--color-text-secondary,#9aa3b2);flex-shrink:0;", text: "Experiment:" }));
        wrap.appendChild(select(exps, currentId));
        const reload = el("button", { class: "testing-results-btn comfymodal-secondary-btn", text: "Reload" });
        reload.addEventListener("click", () => location.reload());
        wrap.appendChild(reload);
      } catch (e) {
        wrap.appendChild(status("Could not list experiments: " + (e.message || e), "error"));
      }
    };
    function select(exps, currentId) {
      const sel = el("select", { class: "testing-results-select comfymodal-input", style: "flex:1;min-width:120px;" });
      sel.appendChild(el("option", { value: "", text: "Select\u2026" }));
      exps.forEach((e) => {
        const o = el("option", { value: e.experiment_id, text: (e.definition && e.definition.name) || e.experiment_id });
        if (e.experiment_id === currentId) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener("change", () => {
        window.location.hash = `#experiment=${encodeURIComponent(sel.value)}`;
        window.location.reload();
      });
      return sel;
    }
    refresh();
    return wrap;
  }

  // ─── getTotalCells with snapshot-reference caching ───
  let _totalCellsCache = null;
  let _totalCellsSnapRef = null;

  function getTotalCells(events, snap) {
    if (_totalCellsCache !== null && _totalCellsSnapRef === snap) {
      return _totalCellsCache;
    }
    if (snap && snap.total_cells) {
      _totalCellsCache = snap.total_cells;
      _totalCellsSnapRef = snap;
      return _totalCellsCache;
    }
    if (snap && snap.cell_visible) {
      const cellCount = Object.keys(snap.cell_visible).length;
      if (cellCount > 0) {
        _totalCellsCache = cellCount;
        _totalCellsSnapRef = snap;
        return _totalCellsCache;
      }
    }
    if (events && events.length) {
      const started = events.find((e) => e.type === "experiment.started" || e.type === "experiment.resumed");
      if (started && started.payload && started.payload.total_cells) {
        _totalCellsCache = started.payload.total_cells;
        _totalCellsSnapRef = snap;
        return _totalCellsCache;
      }
    }
    _totalCellsCache = null;
    _totalCellsSnapRef = snap;
    return null;
  }

  function computeAggregatePct(cells) {
    if (!cells || typeof cells !== "object") return null;
    const values = [];
    Object.values(cells).forEach((cell) => {
      if (cell && typeof cell.pct === "number" && isFinite(cell.pct)) {
        values.push(Math.max(0, Math.min(100, cell.pct)));
      }
    });
    if (values.length === 0) return null;
    const sum = values.reduce((a, b) => a + b, 0);
    return Math.round(sum / values.length);
  }

  function updateSummary(shell, snap, events) {
    const c = shell.querySelector('[data-testid="completed"]');
    const f = shell.querySelector('[data-testid="failed"]');
    const s = shell.querySelector('[data-testid="skipped"]');
    const st = shell.querySelector('[data-testid="status"]');
    const counters = (snap && snap.counters) || {};
    const totalCells = getTotalCells(events, snap);
    const total = totalCells !== null
      ? totalCells
      : (counters.completed || 0) + (counters.failed || 0) + (counters.skipped || 0) + (counters.interrupted || 0);
    if (c) c.textContent = `${counters.completed || 0} / ${total}`;
    if (f) f.textContent = `${counters.failed || 0}`;
    if (s) s.textContent = `${counters.skipped || 0}`;
    if (st) st.textContent = `${(snap && snap.status) || "draft"}`;
  }

  function updateCheckpoints(shell, snap, events) {
    const list = shell.querySelector('[data-testid="checkpoint-list"]');
    if (!list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    const cks = (snap && snap.checkpoints) || {};
    const cellByCk = {};
    if (snap && snap.attempts) {
      Object.values(snap.attempts).forEach((att) => {
        const ckId = att.checkpoint_id || "_unknown";
        cellByCk[ckId] = (cellByCk[ckId] || 0) + 1;
      });
    }
    Object.keys(cks).forEach((id) => {
      const c = cks[id];
      const cellCount = cellByCk[id] || 0;
      const ckProgress = (((window.__comfymodal_worker_progress || {}).checkpoints || {})[id]) || null;
      const pct = (ckProgress && typeof ckProgress.cells === "object")
        ? computeAggregatePct(ckProgress.cells)
        : null;
      const progressEls = (pct === null)
        ? []
        : [
            el("div", {
              class: "testing-results-progress-bar-wrap comfymodal-progress-bar",
              role: "progressbar",
              "aria-label": `checkpoint ${id} progress`,
              "aria-valuemin": "0",
              "aria-valuemax": "100",
              "aria-valuenow": String(pct),
            }, [
              el("div", { class: "comfymodal-progress-fill",
                style: `width: ${pct}%` }),
            ]),
          ];
      list.appendChild(el("div", { class: "testing-results-checkpoint-card" }, [
        el("span", { class: "testing-results-checkpoint-id", style: "font-size:var(--font-size-xs,11px);color:var(--color-text-primary,#e1e4ea);font-weight:var(--font-weight-medium,500);", text: id }),
        el("span", { class: "testing-results-checkpoint-status", style: "font-size:var(--font-size-xs,11px);color:var(--color-text-muted,#6f7785);", text: c.status || "?" }),
        ...progressEls,
        el("span", { class: "testing-results-checkpoint-cells", style: "font-size:var(--font-size-xs,11px);color:var(--color-text-muted,#6f7785);", text: `${cellCount} cell(s)` }),
      ]));
    });
    if (Object.keys(cks).length === 0 && snap && snap.status !== "draft") {
      list.appendChild(el("div", { class: "testing-results-checkpoint-card testing-results-checkpoint-idle", text: "No active checkpoints" }));
    }
  }

  function updateProgressBar(shell, snap, events) {
    updateSummary(shell, snap, events);
    updateCheckpoints(shell, snap, events);
  }

  function getAssetId(attempt) {
    return (attempt && (attempt.primary_asset_id || (attempt.asset_ids && attempt.asset_ids[0]))) || null;
  }

  // ─── Selection state ───
  const SELECTION_LIMIT = 2;
  let selection = [];

  function addToSelection(entry) {
    const idx = selection.findIndex((s) => s.cell_key === entry.cell_key);
    if (idx >= 0) {
      selection.splice(idx, 1);
    } else {
      selection.push(entry);
      if (selection.length > SELECTION_LIMIT) selection.shift();
    }
    window.dispatchEvent(new CustomEvent("testing-selection-changed", { detail: selection }));
  }

  function getModelShortName(attempt) {
    return (attempt && attempt.model) || (attempt && attempt.main_triple && attempt.main_triple.unet) || "";
  }

  function getCellRuntime(attempt) {
    if (attempt && attempt.duration) {
      const sec = Math.round(attempt.duration / 1000);
      if (sec < 60) return `${sec}s`;
      if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
      return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
    }
    return "";
  }

  function renderCellCard(cell, attempt, apiBase, cellIndex) {
    const assetId = getAssetId(attempt);
    const cellStatus = (attempt && attempt.status) || "pending";
    const errorText = (attempt && cellStatus === "failed" && attempt.error)
      ? String(attempt.error)
      : null;
    const modelName = getModelShortName(attempt);
    const runtime = getCellRuntime(attempt);
    const card = el("div", {
      class: `testing-results-cell testing-results-cell-${cellStatus}`,
      "data-cell-key": cell.cell_key,
      "data-testid": "cell-card",
      "data-cell-status": cellStatus,
    }, [
      el("div", { class: "testing-results-cell-thumb" }, [
        assetId
          ? el("img", { src: `${apiBase}/assets/${encodeURIComponent(assetId)}`, class: "testing-results-cell-img", alt: "cell output" })
          : el("div", { class: "testing-results-cell-thumb-placeholder", text: cellStatus }),
        cellIndex != null
          ? el("span", { class: "testing-results-cell-attempt", text: `#${cellIndex + 1}` })
          : null,
      ]),
      el("div", { class: "testing-results-cell-meta" }, [
        el("span", { class: "testing-results-cell-prompt", text: (cell.axis_values && cell.axis_values.prompt) || cell.cell_key.slice(0, 12) }),
        el("div", { style: "display:flex;gap:8px;font-size:var(--font-size-xs,11px);color:var(--color-text-muted,#6f7785);flex-wrap:wrap;" }, [
          el("span", { class: "testing-results-cell-seed", text: `seed ${(cell.axis_values && cell.axis_values.seed) || "?"}` }),
          modelName ? el("span", { class: "testing-results-cell-model", text: modelName }) : null,
          runtime ? el("span", { class: "testing-results-cell-runtime", text: runtime }) : null,
        ]),
      ]),
      errorText
        ? el("div", {
            class: "testing-results-cell-error",
            role: "alert",
            "data-testid": "cell-error",
            title: errorText,
            text: errorText.length > 80 ? `${errorText.slice(0, 77)}...` : errorText,
          })
        : null,
    ]);
    card.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      addToSelection({
        cell_key: cell.cell_key,
        asset_id: assetId,
        attempt_id: (attempt && attempt.attempt_id) || "",
        prompt: (cell.axis_values && cell.axis_values.prompt) || "",
        lora: cell.lora_selection_id || "",
      });
    });
    card.addEventListener("dblclick", () => {
      addToSelection({
        cell_key: cell.cell_key,
        asset_id: assetId,
        attempt_id: (attempt && attempt.attempt_id) || "",
        prompt: (cell.axis_values && cell.axis_values.prompt) || "",
        lora: cell.lora_selection_id || "",
      });
    });
    return card;
  }

  function renderGrid(shell, evs, apiBase) {
    const grid = shell.querySelector('[data-testid="grid-body"]');
    if (!grid) return;
    while (grid.firstChild) grid.removeChild(grid.firstChild);
    const cellMap = {};
    evs.forEach((ev) => {
      const t = ev.type;
      const p = ev.payload || {};
      if (t === "cell.attempt_created") {
        cellMap[p.cell_key] = { attempt: p };
      } else if (t === "cell.completed" || t === "cell.failed" || t === "cell.interrupted") {
        const prev = cellMap[p.cell_key] || {};
        cellMap[p.cell_key] = { cell: { cell_key: p.cell_key, ...(prev.cell || {}) }, attempt: { ...(prev.attempt || {}), ...p, status: t.split(".")[1] } };
      }
    });
    const cks = {};
    Object.values(cellMap).forEach((entry) => {
      const ck = (entry.attempt && entry.attempt.checkpoint_id) || "_unknown";
      cks[ck] = cks[ck] || [];
      cks[ck].push(entry);
    });
    Object.keys(cks).forEach((ck) => {
      const group = el("div", { class: "testing-results-group" }, [
        el("h4", { style: "font-size:var(--font-size-sm,12px);font-weight:var(--font-weight-medium,500);color:var(--color-text-secondary,#9aa3b2);margin:0 0 var(--space-sm,8px);", text: `Checkpoint ${ck}` }),
        el("div", { class: "testing-results-row", style: "display:flex;flex-wrap:wrap;gap:var(--space-sm,8px);" }),
      ]);
      const row = group.querySelector(".testing-results-row");
      cks[ck].forEach((entry, idx) => row.appendChild(renderCellCard(entry.cell || { cell_key: "_" }, entry.attempt, apiBase, idx)));
      grid.appendChild(group);
    });
    if (Object.keys(cks).length === 0) {
      grid.appendChild(el("div", { class: "testing-results-empty-state", text: "No cells yet — start an experiment." }));
    }
  }

  function renderComparison(shell, apiBase) {
    const body = shell.querySelector('[data-testid="compare-body"]');
    if (!body) return;
    while (body.firstChild) body.removeChild(body.firstChild);
    if (selection.length === 0) {
      body.appendChild(el("p", { class: "testing-results-empty-state",
        text: "Right-click two images to compare them here" }));
      return;
    }
    if (selection.length === 1) {
      body.appendChild(el("p", { class: "testing-results-empty-state",
        text: "Right-click a second image to compare" }));
      return;
    }
    const a = selection[selection.length - 2];
    const b = selection[selection.length - 1];
    if (!a.asset_id || !b.asset_id) {
      body.appendChild(el("p", { class: "testing-results-empty-state",
        text: "One or both cells have no asset yet — wait for completion." }));
      return;
    }
    import("./testing-ab-slider.js").then((m) => {
      while (body.firstChild) body.removeChild(body.firstChild);
      const slider = m.ab_slider_render(body, {
        aSrc: `${apiBase}/assets/${encodeURIComponent(a.asset_id)}`,
        bSrc: `${apiBase}/assets/${encodeURIComponent(b.asset_id)}`,
        aLabel: a.prompt || a.cell_key,
        bLabel: b.prompt || b.cell_key,
      });
      slider.on_fullscreen = () => m.ab_slider_open_fullscreen({
        aSrc: `${apiBase}/assets/${encodeURIComponent(a.asset_id)}`,
        bSrc: `${apiBase}/assets/${encodeURIComponent(b.asset_id)}`,
        aLabel: a.prompt || a.cell_key,
        bLabel: b.prompt || b.cell_key,
      });
    });
  }

  // ── Results tab render body ──

  if (!rootEl) throw new Error("results_tab_render: rootEl is required");
  const apiBase = options.apiBase || "/comfymodal";
  let experimentId = options.experimentId || (() => {
    const m = window.location.hash.match(/experiment=([^&]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  })();

  while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);
  const shell = el("div", { class: "testing-results-root" });

  // Five operational zones
  shell.appendChild(commandBarSection(apiBase, experimentId));
  shell.appendChild(summarySection());
  shell.appendChild(progressSection());
  shell.appendChild(gridSection());
  shell.appendChild(comparisonSlotSection(apiBase));
  rootEl.appendChild(shell);

  let lastSeq = 0;
  let pollTimer = null;
  let snapshot = null;
  let lastEvents = [];

  async function refreshSnapshot() {
    if (!experimentId) return;
    try {
      const data = await fetchJson(`${apiBase}/experiments/${encodeURIComponent(experimentId)}`);
      if (data && data.snapshot) {
        snapshot = data.snapshot;
        lastEvents = data.events || [];
        updateProgressBar(shell, snapshot, lastEvents);
        if (lastEvents.length) {
          renderGrid(shell, lastEvents, apiBase);
        }
      }
    } catch (e) {
      console.error("snapshot fetch failed", e);
    }
  }

  async function pollNewEvents() {
    if (!experimentId) return;
    try {
      const data = await fetchJson(`${apiBase}/experiments/${encodeURIComponent(experimentId)}/events?after=${lastSeq}`);
      const evs = (data && data.events) || [];
      const progress = (data && data.progress) || null;
      if (progress) {
        window.__comfymodal_worker_progress = progress;
      }
      if (evs.length) {
        lastSeq = evs[evs.length - 1].sequence || lastSeq;
        await refreshSnapshot();
      } else if (snapshot) {
        updateProgressBar(shell, snapshot, lastEvents);
      }
      if (progress) {
        updateProgressBar(shell, snapshot, lastEvents);
      }
    } catch (e) {
      console.error("event poll failed", e);
    }
  }

  // Initial load
  refreshSnapshot();
  // Poll every 1.5s
  pollTimer = setInterval(pollNewEvents, 1500);

  // Listen for selection changes and re-render the comparison
  const _selectionListener = () => renderComparison(shell, apiBase);
  window.addEventListener("testing-selection-changed", _selectionListener);

  // Event delegation for comparison action buttons
  shell.addEventListener("click", (ev) => {
    const compareActions = ev.target.closest(".testing-results-compare-actions");
    if (!compareActions) return;
    const btn = ev.target.closest("[data-control]");
    if (!btn) return;
    const action = btn.getAttribute("data-control");
    if (action === "compare-swap") {
      selection.reverse();
      renderComparison(shell, apiBase);
    } else if (action === "compare-fullscreen") {
      if (selection.length === 2 && selection[0].asset_id && selection[1].asset_id) {
        import("./testing-ab-slider.js").then((m) => m.ab_slider_open_fullscreen({
          aSrc: `${apiBase}/assets/${encodeURIComponent(selection[0].asset_id)}`,
          bSrc: `${apiBase}/assets/${encodeURIComponent(selection[1].asset_id)}`,
          aLabel: selection[0].prompt || selection[0].cell_key,
          bLabel: selection[1].prompt || selection[1].cell_key,
        }));
      }
    }
  });

  return {
    rootEl: shell,
    stop() {
      if (pollTimer) clearInterval(pollTimer);
      if (_selectionListener) {
        window.removeEventListener("testing-selection-changed", _selectionListener);
      }
    },
    updateProgress(snap, evs) { snapshot = snap; if (evs) lastEvents = evs; updateProgressBar(shell, snap, lastEvents); },
  };
}
