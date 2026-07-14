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
      el("div", { class: "testing-results-gallery-layout" }, [
        el("div", { class: "testing-results-gallery-body-wrap" }, [
          el("div", { class: "testing-results-grid-body", "data-testid": "grid-body" }, [
            el("div", { class: "testing-results-empty-state", text: "Select an experiment above and start it. Cells appear here as they complete." }),
          ]),
        ]),
        el("div", { class: "testing-results-side-panel testing-results-side-panel-hidden", "data-testid": "detail-panel" }),
      ]),
      el("div", { class: "testing-results-progress-bars", "data-testid": "progress-bars" }),
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
    renderProgressBars(shell, snap, events);
  }

  function getAssetId(attempt) {
    return (attempt && (attempt.primary_asset_id || (attempt.asset_ids && attempt.asset_ids[0]))) || null;
  }

  function resolveCellImageUrl(attempt, apiBase) {
    if (!attempt) return null;
    if (attempt.primary_asset_id) {
      return apiBase + "/assets/" + encodeURIComponent(attempt.primary_asset_id);
    }
    if (attempt.asset_ids && attempt.asset_ids.length > 0) {
      return apiBase + "/assets/" + encodeURIComponent(attempt.asset_ids[0]);
    }
    if (attempt.output_paths && attempt.output_paths.length > 0) {
      return apiBase + "/studio/outputs/" + encodeURIComponent(attempt.output_paths[0]);
    }
    if (attempt.output_path) {
      return apiBase + "/studio/outputs/" + encodeURIComponent(attempt.output_path);
    }
    return null;
  }

  // ─── Selection state ───
  const SELECTION_LIMIT = 2;
  let selection = [];
  // Detail panel: single cell clicked to show full metadata
  let _detailCell = null;
  let _varyingAxes = [];

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

  function renderCellCard(cell, attempt, apiBase, cellIndex, compact = false) {
    const assetId = getAssetId(attempt);
    const imageUrl = assetId
      ? apiBase + "/assets/" + encodeURIComponent(assetId)
      : resolveCellImageUrl(attempt, apiBase);
    const cellStatus = (attempt && attempt.status) || "pending";
    const errorText = (attempt && cellStatus === "failed" && attempt.error)
      ? String(attempt.error)
      : null;
    const modelName = getModelShortName(attempt);
    const runtime = getCellRuntime(attempt);
    const card = el("div", {
      class: `testing-results-cell testing-results-cell-${cellStatus}${compact ? " testing-results-cell-compact" : ""}`,
      "data-cell-key": cell.cell_key,
      "data-testid": "cell-card",
      "data-cell-status": cellStatus,
    }, [
      el("div", { class: "testing-results-cell-thumb", style: "position:relative;" }, [
        imageUrl
          ? el("img", { src: imageUrl, class: "testing-results-cell-img", alt: "cell output" })
          : el("div", { class: "testing-results-cell-thumb-placeholder", text: cellStatus === "running" ? "" : cellStatus }),
        cellStatus === "running"
          ? el("div", { class: "testing-results-running-spinner" })
          : null,
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
        image_url: imageUrl,
        attempt_id: (attempt && attempt.attempt_id) || "",
        prompt: (cell.axis_values && cell.axis_values.prompt) || "",
        lora: cell.lora_selection_id || "",
      });
    });
    card.addEventListener("dblclick", () => {
      addToSelection({
        cell_key: cell.cell_key,
        asset_id: assetId,
        image_url: imageUrl,
        attempt_id: (attempt && attempt.attempt_id) || "",
        prompt: (cell.axis_values && cell.axis_values.prompt) || "",
        lora: cell.lora_selection_id || "",
      });
    });
    card.addEventListener("click", (ev) => {
      if (ev.defaultPrevented) return;
      _detailCell = { cell, attempt, cellIndex };
      _varyingAxes = _varyingAxes || [];
      renderDetailPanel(shell, apiBase);
    });
    return card;
  }

  // ── Detail Panel (side panel for cell metadata) ──────────────

  function closeDetailPanel() {
    _detailCell = null;
    renderDetailPanel(shell, apiBase);
  }

  function renderDetailPanel(shell, apiBase) {
    const panel = shell.querySelector('[data-testid="detail-panel"]');
    if (!panel) return;
    while (panel.firstChild) panel.removeChild(panel.firstChild);
    if (!_detailCell) {
      panel.classList.add("testing-results-side-panel-hidden");
      return;
    }
    panel.classList.remove("testing-results-side-panel-hidden");
    const entry = _detailCell;
    const c = entry.cell || {};
    const att = entry.attempt || {};
    const ax = c.axis_values || {};
    const status = att.status || "pending";
    const cellIdx = entry.cellIndex;
    const statusClass = status === "completed" ? "success"
      : status === "failed" ? "danger"
      : status === "running" || status === "pending" ? "warning"
      : "info";
    panel.appendChild(el("div", { class: "testing-results-detail-header" }, [
      el("span", { class: "testing-results-detail-title", text: "Cell Details" }),
      el("button", { class: "testing-results-detail-close", text: "\u00d7",
        onclick: closeDetailPanel }),
    ]));
    const body = el("div", { class: "testing-results-detail-body" });
    // Cell key row
    body.appendChild(el("div", { class: "testing-results-detail-row" }, [
      el("span", { class: "testing-results-detail-label", text: "Cell Key" }),
      el("span", { class: "testing-results-detail-value", text: c.cell_key || "?" }),
    ]));
    // Index row
    if (cellIdx != null) {
      body.appendChild(el("div", { class: "testing-results-detail-row" }, [
        el("span", { class: "testing-results-detail-label", text: "Index" }),
        el("span", { class: "testing-results-detail-value", text: String(cellIdx + 1) }),
      ]));
    }
    // Status row
    body.appendChild(el("div", { class: "testing-results-detail-row" }, [
      el("span", { class: "testing-results-detail-label", text: "Status" }),
      el("span", { class: "comfymodal-status-badge " + statusClass, text: status }),
    ]));
    // Attempt ID
    if (att.attempt_id) {
      body.appendChild(el("div", { class: "testing-results-detail-row" }, [
        el("span", { class: "testing-results-detail-label", text: "Attempt ID" }),
        el("span", { class: "testing-results-detail-value", text: att.attempt_id }),
      ]));
    }
    // Error
    if (att.error) {
      body.appendChild(el("div", { class: "testing-results-detail-row" }, [
        el("span", { class: "testing-results-detail-label", text: "Error" }),
        el("span", { class: "testing-results-detail-value", style: "color:var(--color-danger,#ef4444);", text: String(att.error).slice(0, 120) }),
      ]));
    }
    // All axis values (parameters)
    var axisKeys = Object.keys(ax);
    axisKeys.forEach(function (k) {
      var isAxis = _varyingAxes.indexOf(k) >= 0;
      var v = ax[k];
      var vStr = v === null || v === undefined ? "?" : (typeof v === "object" ? JSON.stringify(v) : String(v));
      body.appendChild(el("div", {
        class: "testing-results-detail-row" + (isAxis ? " testing-results-detail-axis" : ""),
      }, [
        el("span", { class: "testing-results-detail-label", text: k }),
        el("span", { class: "testing-results-detail-value", text: vStr }),
      ]));
    });
    panel.appendChild(body);
  }

  // ── Progress bars (image progress + total run progress) ──────

  function renderProgressBars(shell, snap, events) {
    var barsEl = shell.querySelector('[data-testid="progress-bars"]');
    if (!barsEl) return;
    while (barsEl.firstChild) barsEl.removeChild(barsEl.firstChild);
    // Image progress: aggregate pct from worker progress cells
    var wp = window.__comfymodal_worker_progress || null;
    var imagePct = null;
    if (wp && wp.cells && typeof wp.cells === "object") {
      imagePct = computeAggregatePct(wp.cells);
    }
    var counters = (snap && snap.counters) || {};
    var totalCells = getTotalCells(events, snap);
    // Terminal count = every finished cell regardless of outcome
    var terminal = (counters.completed || 0) + (counters.failed || 0) + (counters.skipped || 0) + (counters.interrupted || 0);
    var totalPct = totalCells !== null && totalCells > 0
      ? Math.min(100, Math.round((terminal / totalCells) * 100))
      : null;
    // Image progress bar
    barsEl.appendChild(el("div", { class: "testing-results-progress-bar-row" }, [
      el("div", { class: "testing-results-progress-bar-header" }, [
        el("span", { text: "Image Progress" }),
        el("span", { class: "testing-results-progress-bar-pct",
          text: imagePct !== null ? imagePct + "%" : "queued" }),
      ]),
      el("div", { class: "testing-results-progress-track" }, [
        el("div", {
          class: "testing-results-progress-fill testing-results-progress-fill-image",
          style: "width:" + (imagePct !== null ? imagePct : 0) + "%;",
        }),
      ]),
    ]));
    // Total progress bar
    barsEl.appendChild(el("div", { class: "testing-results-progress-bar-row" }, [
      el("div", { class: "testing-results-progress-bar-header" }, [
        el("span", { text: "Total Progress" }),
        el("span", { class: "testing-results-progress-bar-pct",
          text: totalPct !== null
            ? terminal + " / " + totalCells + " (" + totalPct + "%)"
            : terminal > 0 ? terminal + " done" : "queued" }),
      ]),
      el("div", { class: "testing-results-progress-track" }, [
        el("div", {
          class: "testing-results-progress-fill testing-results-progress-fill-total",
          style: "width:" + (totalPct !== null ? totalPct : 0) + "%;",
        }),
      ]),
    ]));
  }

  // ── Results Grouping Adapter ──────────────────────────────────
  //
  // Groups cells by backend normalized_dimensions metadata when available,
  // falling back to checkpoint-based (technical) grouping.
  // Preserves A/B comparison and selection behavior intact.

  const GROUP_BY_WORKFLOW = "group-by-workflow";
  const GROUP_BY_MODEL_STACK = "group-by-model-stack";
  const GROUP_BY_LORA = "group-by-lora";

  function resolveGroupingStrategy(snap) {
    const dims = (snap && snap.normalized_dimensions) || null;
    if (dims && Array.isArray(dims) && dims.length > 0) {
      return {
        type: "dimension",
        dimensions: dims,
        adapterClass: "testing-results-grouping-adapter",
      };
    }
    return {
      type: "technical",
      dimensions: [],
      adapterClass: "testing-results-technical",
    };
  }

  function getDimValue(attempt, dimKey) {
    if (!attempt || !attempt.normalized_values) return null;
    return attempt.normalized_values[dimKey] || null;
  }

  function groupByDimensions(cellMap, dimensions) {
    const groups = {};
    Object.values(cellMap).forEach((entry) => {
      const attempt = entry.attempt || {};
      const parts = dimensions.map((d) => getDimValue(attempt, d) || "_unknown");
      const groupKey = parts.join(" / ");
      groups[groupKey] = groups[groupKey] || [];
      groups[groupKey].push(entry);
    });
    return groups;
  }

  function groupByCheckpoint(cellMap) {
    const groups = {};
    Object.values(cellMap).forEach((entry) => {
      const ck = (entry.attempt && entry.attempt.checkpoint_id) || "_unknown";
      groups[ck] = groups[ck] || [];
      groups[ck].push(entry);
    });
    return groups;
  }

  function renderGroupLabel(groupKey, strategy) {
    if (strategy.type === "technical") {
      return "Checkpoint " + groupKey;
    }
    const parts = groupKey.split(" / ");
    return strategy.dimensions.map((d, i) => {
      const val = parts[i] || "_";
      return d + ": " + val;
    }).join(" | ");
  }

  // ── Axis-based Results Rendering ────────────────────────────
  //
  // Uses experiment.created payload.compilation.cells as the authoritative
  // cell list with axis_values metadata. Merges latest attempt state from
  // snapshot.attempts and snapshot.cell_visible. Renders in layouts based
  // on the number of varying axes (0 = technical fallback, 1 = sequence,
  // 2 = matrix, 3 = grouped matrices, 4 = nested grouped matrices).

  function getCompilationCells(evs) {
    if (!evs) return [];
    const createdEv = evs.find(function (e) { return e.type === "experiment.created"; });
    if (!createdEv || !createdEv.payload) return [];
    const compilation = createdEv.payload.compilation;
    if (!compilation || !Array.isArray(compilation.cells)) return [];
    return compilation.cells;
  }

  function mergeCellState(compilationCells, evs, snap) {
    // Build event-derived attempt map (latest event per cell_key wins)
    var eventAttempts = {};
    if (evs) {
      evs.forEach(function (ev) {
        var t = ev.type;
        var p = ev.payload || {};
        var ck = p.cell_key;
        if (!ck) return;
        if (t === "experiment.created") return;
        if (t === "cell.attempt_created") {
          eventAttempts[ck] = eventAttempts[ck] || {};
          eventAttempts[ck].attempt = Object.assign({}, p);
          eventAttempts[ck].attempt.status = "pending";
        } else if (["cell.completed", "cell.failed", "cell.interrupted", "cell.skipped"].indexOf(t) >= 0) {
          var status = t.split(".")[1];
          var prev = eventAttempts[ck] || {};
          eventAttempts[ck] = {
            cell: { cell_key: ck },
            attempt: Object.assign({}, prev.attempt || {}, p, { status: status }),
          };
        }
      });
    }
    // Merge compilation cells with event and snapshot data
    return compilationCells.map(function (compCell) {
      var ck = compCell.cell_key;
      var evData = eventAttempts[ck] || {};
      var snapAtt = (snap && snap.attempts && snap.attempts[ck]) || {};
      var visibleStatus = (snap && snap.cell_visible && snap.cell_visible[ck]) || null;
      // Build attempt: event data for rich fields, snapshot for latest state
      var attempt = Object.assign({}, evData.attempt || {}, snapAtt);
      // Prefer snapshot cell_visible status (authoritative), fall back
      attempt.status = visibleStatus || snapAtt.status || (evData.attempt ? evData.attempt.status : null) || "pending";
      return {
        cell: Object.assign({ cell_key: ck, axis_values: compCell.axis_values || {} }, compCell),
        attempt: attempt,
      };
    });
  }

  function computeVaryingAxes(entries) {
    if (!entries || entries.length === 0) return { axes: [], valueSets: {} };
    var allValues = {};
    var firstSeenKeys = [];
    for (var i = 0; i < entries.length; i++) {
      var av = entries[i].cell.axis_values || {};
      for (var key in av) {
        if (!av.hasOwnProperty(key)) continue;
        if (!allValues[key]) {
          allValues[key] = new Set();
          firstSeenKeys.push(key);
        }
        var v = av[key];
        var sv = typeof v === "object" ? JSON.stringify(v) : String(v);
        allValues[key].add(sv);
      }
    }
    var varying = [];
    for (var j = 0; j < firstSeenKeys.length; j++) {
      var k = firstSeenKeys[j];
      if (allValues[k].size > 1) {
        varying.push(k);
      }
    }
    return { axes: varying, valueSets: allValues };
  }

  function getAxisValueLabel(entry, axisKey) {
    var av = entry.cell.axis_values || {};
    var v = av[axisKey];
    if (v === null || v === undefined) return "?";
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }

  function formatAxisLabel(axisKey, axisValue) {
    return axisKey + ": " + axisValue;
  }

  // ── Fallback: render from events (old behavior) ─────────────

  function renderFromEvents(grid, evs, apiBase, snap) {
    var cellMap = {};
    if (evs) {
      evs.forEach(function (ev) {
        var t = ev.type;
        var p = ev.payload || {};
        if (t === "cell.attempt_created") {
          cellMap[p.cell_key] = { attempt: p };
        } else if (["cell.completed", "cell.failed", "cell.interrupted", "cell.skipped"].indexOf(t) >= 0) {
          var prev = cellMap[p.cell_key] || {};
          cellMap[p.cell_key] = {
            cell: Object.assign({ cell_key: p.cell_key }, prev.cell || {}),
            attempt: Object.assign({}, prev.attempt || {}, p, { status: t.split(".")[1] }),
          };
        }
      });
    }
    var strategy = resolveGroupingStrategy(snap);
    var groups = strategy.type === "dimension"
      ? groupByDimensions(cellMap, strategy.dimensions)
      : groupByCheckpoint(cellMap);
    var groupKeys = Object.keys(groups);
    groupKeys.forEach(function (groupKey) {
      var group = el("div", {
        class: "testing-results-group " + strategy.adapterClass,
        "data-group-strategy": strategy.type,
      }, [
        el("h4", {
          class: strategy.type === "technical" ? "technical-view" : "",
          style: "font-size:var(--font-size-sm,12px);font-weight:var(--font-weight-medium,500);color:var(--color-text-secondary,#9aa3b2);margin:0 0 var(--space-sm,8px);",
          text: renderGroupLabel(groupKey, strategy),
        }),
        el("div", { class: "testing-results-row", style: "display:flex;flex-wrap:wrap;gap:var(--space-sm,8px);" }),
      ]);
      var row = group.querySelector(".testing-results-row");
      groups[groupKey].forEach(function (entry, idx) {
        row.appendChild(renderCellCard(entry.cell || { cell_key: "_" }, entry.attempt, apiBase, idx));
      });
      grid.appendChild(group);
    });
    if (groupKeys.length === 0) {
      grid.appendChild(el("div", { class: "testing-results-empty-state", text: "No cells yet — start an experiment." }));
    }
  }

  // ── 0 axes: technical fallback (checkpoint groups) ──────────

  function renderFallbackGroups(grid, entries, apiBase, snap) {
    var groups = {};
    entries.forEach(function (entry) {
      var ck = (entry.attempt && entry.attempt.checkpoint_id) || (entry.cell && entry.cell.checkpoint_id) || "_unknown";
      groups[ck] = groups[ck] || [];
      groups[ck].push(entry);
    });
    var groupKeys = Object.keys(groups);
    groupKeys.forEach(function (groupKey) {
      var group = el("div", {
        class: "testing-results-group testing-results-technical",
        "data-group-strategy": "technical",
      }, [
        el("h4", {
          class: "technical-view",
          style: "font-size:var(--font-size-sm,12px);font-weight:var(--font-weight-medium,500);color:var(--color-text-secondary,#9aa3b2);margin:0 0 var(--space-sm,8px);",
          text: "Checkpoint " + groupKey,
        }),
        el("div", { class: "testing-results-row", style: "display:flex;flex-wrap:wrap;gap:var(--space-sm,8px);" }),
      ]);
      var row = group.querySelector(".testing-results-row");
      groups[groupKey].forEach(function (entry, idx) {
        row.appendChild(renderCellCard(entry.cell || { cell_key: "_" }, entry.attempt, apiBase, idx));
      });
      grid.appendChild(group);
    });
    if (groupKeys.length === 0) {
      grid.appendChild(el("div", { class: "testing-results-empty-state", text: "No cells yet — start an experiment." }));
    }
  }

  // ── First-seen order (preserve compilation order) ──────────

  function uniqueInOrder(entries, accessor) {
    var seen = {};
    var result = [];
    for (var i = 0; i < entries.length; i++) {
      var val = accessor(entries[i]);
      if (!seen.hasOwnProperty(val)) {
        seen[val] = true;
        result.push(val);
      }
    }
    return result;
  }

  // ── 1 varying axis: labeled sequence ────────────────────────

  function renderLabeledSequence(grid, entries, axes, apiBase) {
    var axisKey = axes[0];
    var wrap = el("div", { class: "testing-results-axis-sequence" });
    entries.forEach(function (entry, idx) {
      var labelText = formatAxisLabel(axisKey, getAxisValueLabel(entry, axisKey));
      var item = el("div", { class: "testing-results-axis-sequence-item" }, [
        el("div", { class: "testing-results-axis-label", text: labelText }),
        renderCellCard(entry.cell, entry.attempt, apiBase, idx, false),
      ]);
      wrap.appendChild(item);
    });
    grid.appendChild(wrap);
  }

  // ── 2 varying axes: matrix ──────────────────────────────────

  function buildMatrix(entries, rowAxis, colAxis) {
    var rowValues = uniqueInOrder(entries, function (e) { return getAxisValueLabel(e, rowAxis); });
    var colValues = uniqueInOrder(entries, function (e) { return getAxisValueLabel(e, colAxis); });
    var grid = {};
    entries.forEach(function (entry) {
      var rv = getAxisValueLabel(entry, rowAxis);
      var cv = getAxisValueLabel(entry, colAxis);
      var ri = rowValues.indexOf(rv);
      var ci = colValues.indexOf(cv);
      if (ri >= 0 && ci >= 0) {
        grid[ri + "," + ci] = entry;
      }
    });
    return { rowValues: rowValues, colValues: colValues, grid: grid };
  }

  function renderMatrixLayout(grid, entries, axes, apiBase) {
    var rowAxis = axes[0];
    var colAxis = axes[1];
    var matrix = buildMatrix(entries, rowAxis, colAxis);
    var wrap = el("div", { class: "testing-results-matrix-wrap" });
    var scroll = el("div", { class: "testing-results-matrix-scroll" }, [
      el("table", { class: "testing-results-matrix" }, [
        el("thead", {}, [
          el("tr", {}, [
            el("th", { class: "testing-results-matrix-corner", text: rowAxis + " \\ " + colAxis }),
          ].concat(matrix.colValues.map(function (cv) {
            return el("th", { class: "testing-results-matrix-col-header", text: formatAxisLabel(colAxis, cv) });
          }))),
        ]),
        el("tbody", {}, matrix.rowValues.map(function (rv, ri) {
          return el("tr", {}, [
            el("th", { class: "testing-results-matrix-row-header", text: formatAxisLabel(rowAxis, rv) }),
          ].concat(matrix.colValues.map(function (cv, ci) {
            var entry = matrix.grid[ri + "," + ci];
            if (entry) {
              return el("td", { class: "testing-results-matrix-cell" }, [
                renderCellCard(entry.cell, entry.attempt, apiBase, null, true),
              ]);
            }
            return el("td", { class: "testing-results-matrix-cell testing-results-matrix-empty" });
          })));
        })),
      ]),
    ]);
    wrap.appendChild(scroll);
    grid.appendChild(wrap);
  }

  // ── 3 varying axes: groups by third axis, each with matrix ──

  function renderGroupedMatrixLayout(grid, entries, axes, apiBase) {
    var groupAxis = axes[2];
    var rowAxis = axes[0];
    var colAxis = axes[1];
    var groups = {};
    entries.forEach(function (entry) {
      var gv = getAxisValueLabel(entry, groupAxis);
      groups[gv] = groups[gv] || [];
      groups[gv].push(entry);
    });
    var wrap = el("div", { class: "testing-results-3d-wrapper" });
    var groupKeys = uniqueInOrder(entries, function (e) { return getAxisValueLabel(e, groupAxis); });
    groupKeys.forEach(function (gv) {
      var group = el("div", { class: "testing-results-3d-group" }, [
        el("h4", { class: "testing-results-axis-group-header", text: formatAxisLabel(groupAxis, gv) }),
      ]);
      // Render matrix within each group (reuse matrix builder)
      var matrixWrap = el("div", { class: "testing-results-matrix-wrap" });
      var matrix = buildMatrix(groups[gv], rowAxis, colAxis);
      var scroll = el("div", { class: "testing-results-matrix-scroll" }, [
        el("table", { class: "testing-results-matrix" }, [
          el("thead", {}, [
            el("tr", {}, [
              el("th", { class: "testing-results-matrix-corner", text: rowAxis + " \\ " + colAxis }),
            ].concat(matrix.colValues.map(function (cv) {
              return el("th", { class: "testing-results-matrix-col-header", text: formatAxisLabel(colAxis, cv) });
            }))),
          ]),
          el("tbody", {}, matrix.rowValues.map(function (rv, ri) {
            return el("tr", {}, [
              el("th", { class: "testing-results-matrix-row-header", text: formatAxisLabel(rowAxis, rv) }),
            ].concat(matrix.colValues.map(function (cv, ci) {
              var entry = matrix.grid[ri + "," + ci];
              if (entry) {
                return el("td", { class: "testing-results-matrix-cell" }, [
                  renderCellCard(entry.cell, entry.attempt, apiBase, null, true),
                ]);
              }
              return el("td", { class: "testing-results-matrix-cell testing-results-matrix-empty" });
            })));
          })),
        ]),
      ]);
      matrixWrap.appendChild(scroll);
      group.appendChild(matrixWrap);
      wrap.appendChild(group);
    });
    grid.appendChild(wrap);
  }

  // ── 4 varying axes: nested groups (4th outer, 3rd inner), each with matrix ──

  function renderNestedGroupedMatrixLayout(grid, entries, axes, apiBase) {
    var outerAxis = axes[3];
    var innerAxis = axes[2];
    var rowAxis = axes[0];
    var colAxis = axes[1];
    var outerGroups = {};
    entries.forEach(function (entry) {
      var ov = getAxisValueLabel(entry, outerAxis);
      outerGroups[ov] = outerGroups[ov] || [];
      outerGroups[ov].push(entry);
    });
    var outerWrap = el("div", { class: "testing-results-4d-outer" });
    var outerKeys = uniqueInOrder(entries, function (e) { return getAxisValueLabel(e, outerAxis); });
    outerKeys.forEach(function (ov) {
      var outerGroup = el("div", { class: "testing-results-4d-group" }, [
        el("h4", { class: "testing-results-axis-group-header", text: formatAxisLabel(outerAxis, ov) }),
      ]);
      var innerGroups = {};
      outerGroups[ov].forEach(function (entry) {
        var iv = getAxisValueLabel(entry, innerAxis);
        innerGroups[iv] = innerGroups[iv] || [];
        innerGroups[iv].push(entry);
      });
      var innerWrap = el("div", { class: "testing-results-4d-inner" });
      var innerKeys = uniqueInOrder(outerGroups[ov], function (e) { return getAxisValueLabel(e, innerAxis); });
      innerKeys.forEach(function (iv) {
        var innerGroup = el("div", { class: "testing-results-4d-inner-group" }, [
          el("h5", { class: "testing-results-axis-inner-header", text: formatAxisLabel(innerAxis, iv) }),
        ]);
        var matrix = buildMatrix(innerGroups[iv], rowAxis, colAxis);
        var matrixWrap = el("div", { class: "testing-results-matrix-wrap" });
        var scroll = el("div", { class: "testing-results-matrix-scroll" }, [
          el("table", { class: "testing-results-matrix" }, [
            el("thead", {}, [
              el("tr", {}, [
                el("th", { class: "testing-results-matrix-corner", text: rowAxis + " \\ " + colAxis }),
              ].concat(matrix.colValues.map(function (cv) {
                return el("th", { class: "testing-results-matrix-col-header", text: formatAxisLabel(colAxis, cv) });
              }))),
            ]),
            el("tbody", {}, matrix.rowValues.map(function (rv, ri) {
              return el("tr", {}, [
                el("th", { class: "testing-results-matrix-row-header", text: formatAxisLabel(rowAxis, rv) }),
              ].concat(matrix.colValues.map(function (cv, ci) {
                var entry = matrix.grid[ri + "," + ci];
                if (entry) {
                  return el("td", { class: "testing-results-matrix-cell" }, [
                    renderCellCard(entry.cell, entry.attempt, apiBase, null, true),
                  ]);
                }
                return el("td", { class: "testing-results-matrix-cell testing-results-matrix-empty" });
              })));
            })),
          ]),
        ]);
        matrixWrap.appendChild(scroll);
        innerGroup.appendChild(matrixWrap);
        innerWrap.appendChild(innerGroup);
      });
      outerGroup.appendChild(innerWrap);
      outerWrap.appendChild(outerGroup);
    });
    grid.appendChild(outerWrap);
  }

  // ── >4 axes: fallback message ─────────────────────────────

  function renderTooManyAxes(grid, numAxes) {
    grid.appendChild(el("div", { class: "testing-results-empty-state testing-results-too-many-axes" }, [
      el("p", { style: "font-weight:var(--font-weight-semibold,600);margin:0 0 var(--space-sm,8px);", text: "Too many varying dimensions (" + numAxes + ")" }),
      el("p", { style: "margin:0;font-size:var(--font-size-xs,11px);color:var(--color-text-muted,#6f7785);", text: "The grid view supports up to 4 varying axes. Reduce the number of test values to see results in a matrix layout." }),
    ]));
  }

  // ── Main renderGrid dispatcher ─────────────────────────────

  function renderGrid(shell, evs, apiBase, snap) {
    var grid = shell.querySelector('[data-testid="grid-body"]');
    if (!grid) return;
    while (grid.firstChild) grid.removeChild(grid.firstChild);

    // 1. Get compilation cells from experiment.created event
    var compilationCells = getCompilationCells(evs);

    // 2. If no compilation cells, fall back to event-based rendering
    if (compilationCells.length === 0) {
      renderFromEvents(grid, evs, apiBase, snap);
      _varyingAxes = [];
      renderProgressBars(shell, snap, evs);
      return;
    }

    // 3. Merge compilation cell metadata with attempt state
    var mergedEntries = mergeCellState(compilationCells, evs, snap);

    // 4. Compute varying axes (exclude axes with only one value)
    var vaxes = computeVaryingAxes(mergedEntries);
    var numAxes = vaxes.axes.length;
    _varyingAxes = vaxes.axes;

    // 5. Route to layout based on number of varying axes
    if (numAxes === 0) {
      renderFallbackGroups(grid, mergedEntries, apiBase, snap);
    } else if (numAxes === 1) {
      renderLabeledSequence(grid, mergedEntries, vaxes.axes, apiBase);
    } else if (numAxes === 2) {
      renderMatrixLayout(grid, mergedEntries, vaxes.axes, apiBase);
    } else if (numAxes === 3) {
      renderGroupedMatrixLayout(grid, mergedEntries, vaxes.axes, apiBase);
    } else if (numAxes === 4) {
      renderNestedGroupedMatrixLayout(grid, mergedEntries, vaxes.axes, apiBase);
    } else {
      renderTooManyAxes(grid, numAxes);
    }

    // 6. Reconcile detail panel: refresh _detailCell from fresh merged state
    if (_detailCell && _detailCell.cell && _detailCell.cell.cell_key) {
      var ck = _detailCell.cell.cell_key;
      var updated = null;
      for (var ei = 0; ei < mergedEntries.length; ei++) {
        if (mergedEntries[ei].cell && mergedEntries[ei].cell.cell_key === ck) {
          updated = mergedEntries[ei];
          break;
        }
      }
      if (updated) {
        _detailCell = { cell: updated.cell, attempt: updated.attempt, cellIndex: _detailCell.cellIndex };
        renderDetailPanel(shell, apiBase);
      } else {
        closeDetailPanel();
      }
    }

    // 7. Render progress bars below the grid
    renderProgressBars(shell, snap, evs);
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
    if (!a.image_url || !b.image_url) {
      body.appendChild(el("p", { class: "testing-results-empty-state",
        text: "One or both cells have no image yet — wait for completion." }));
      return;
    }
    import("./testing-ab-slider.js").then((m) => {
      while (body.firstChild) body.removeChild(body.firstChild);
      const slider = m.ab_slider_render(body, {
        aSrc: a.image_url,
        bSrc: b.image_url,
        aLabel: a.prompt || a.cell_key,
        bLabel: b.prompt || b.cell_key,
      });
      slider.on_fullscreen = () => m.ab_slider_open_fullscreen({
        aSrc: a.image_url,
        bSrc: b.image_url,
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
        renderGrid(shell, lastEvents, apiBase, snapshot);
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

  // Escape key closes the detail panel
  const _detailKeyHandler = function (ev) {
    if (ev.key === "Escape" && _detailCell) {
      closeDetailPanel();
    }
  };
  window.addEventListener("keydown", _detailKeyHandler);

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
      if (selection.length === 2 && selection[0].image_url && selection[1].image_url) {
        import("./testing-ab-slider.js").then((m) => m.ab_slider_open_fullscreen({
          aSrc: selection[0].image_url,
          bSrc: selection[1].image_url,
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
      window.removeEventListener("keydown", _detailKeyHandler);
    },
    updateProgress(snap, evs) { snapshot = snap; if (evs) lastEvents = evs; updateProgressBar(shell, snap, lastEvents); },
  };
}
