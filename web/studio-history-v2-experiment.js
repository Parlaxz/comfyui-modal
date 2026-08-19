// Modal Studio — History V2 Experiment Detail
//
// Full page for a single experiment: back button, header with counts and
// axes, retry action, notes, favorite, and the complete cell grid.  The
// grid lays out as a matrix when both axis labels and per-cell axis values
// are known; otherwise it falls back to a simple flow grid.  Every cell is
// always shown — never truncated.  Selecting a cell reveals a detail pane.
//
// All DOM via el() from studio-ui.js; no innerHTML with dynamic data.

import { el } from "./studio-ui.js";
import { _formatDuration } from "./studio-run-normalizer.js";
import { selectDetailAsset, selectFeedAsset } from "./history-v2-repository.js";

// ── Constants / helpers ───────────────────────────────────────────────────

const STATUS_LABELS = {
  completed: "Completed",
  completed_with_failures: "Completed with failures",
  failed: "Failed",
  canceled: "Canceled",
  interrupted: "Interrupted",
  running: "Running",
  queued: "Queued",
};

const CELL_STATUS_ALIASES = {
  completed: "completed", complete: "completed", success: "completed", succeeded: "completed",
  done: "completed", ok: "completed",
  failed: "failed", failure: "failed", error: "failed", errored: "failed",
  canceled: "canceled", cancelled: "canceled", stopped: "canceled",
  interrupted: "interrupted", aborted: "interrupted",
  running: "running", in_progress: "running",
  queued: "queued", pending: "queued", not_started: "queued", scheduled: "queued",
  completed_with_failures: "completed_with_failures", partial: "completed_with_failures",
};

/**
 * Canonical cell status (raw "success" → "completed" etc.).  The detail page
 * never renders the word "partial" and keeps canceled/interrupted/failed
 * distinct.
 */
export function canonicalCellStatus(status) {
  if (status == null) return "queued";
  const key = String(status).toLowerCase().replace(/\s+/g, "_");
  return CELL_STATUS_ALIASES[key] || key;
}

/** Display label for a canonical status. */
export function experimentStatusLabel(status) {
  const key = canonicalCellStatus(status);
  return STATUS_LABELS[key] || (status != null ? String(status) : "Queued");
}

function _statusChip(status) {
  const key = canonicalCellStatus(status);
  const label = experimentStatusLabel(status);
  return el("span", { class: "comfymodal-studio-history-v2-chip status-" + key, text: label });
}

/** Stable cell identity: cell_id when present, else key, else position. */
export function historyCellIdentity(cell, index) {
  if (!cell || typeof cell !== "object") return "cell_" + index;
  return String(cell.cellId || cell.cell_id || cell.key || "cell_" + index);
}

/** Per-cell workflow/version/preset labels (cell-level ids preferred). */
export function cellWorkflowMeta(cell, rec) {
  const parts = { workflow: "", version: "", preset: "" };
  const c = cell && typeof cell === "object" ? cell : {};
  const r = rec || {};
  parts.workflow = String(c.workflowId || c.workflow_id || c.workflow || r.workflow || "");
  parts.version = String(c.workflowVersionId || c.workflow_version_id || c.workflow_version || r.workflowVersion || "");
  parts.preset = String(c.presetId || c.preset_id || c.preset || r.preset || "");
  return parts;
}

/** Attempt count for a cell (attempts[] when the record carries them). */
export function historyCellAttemptCount(cell) {
  if (!cell || typeof cell !== "object") return 0;
  if (Array.isArray(cell.attempts)) return cell.attempts.length;
  if (cell.attemptCount != null) return Number(cell.attemptCount) || 0;
  return 0;
}

export function historyAttemptPurposeLabel(mode) {
  const key = mode == null ? "" : String(mode).toLowerCase();
  if (key === "original") return "Original";
  if (key === "preview") return "Preview";
  return "Run";
}

export function selectExperimentCellAsset(cell) {
  return selectFeedAsset(cell);
}

/**
 * Resume eligible: any interrupted or queued/not-started cell exists AND the
 * experiment is not actively running (a cell in "running").  A "queued"
 * aggregate with queued/not-started cells IS resume-eligible; only actively
 * running experiments suppress Resume.  Failed cells are never resumed.
 */
export function historyResumeEligible(rec) {
  if (!rec) return false;
  const cells = Array.isArray(rec.cells) ? rec.cells : [];
  let hasActive = false;
  let hasEligible = false;
  cells.forEach(function (c) {
    const s = canonicalCellStatus(c && c.status);
    if (s === "running") hasActive = true;
    if (s === "interrupted" || s === "queued") hasEligible = true;
  });
  if (hasActive) return false;
  return hasEligible;
}

/** Only failed cells may be retried. */
export function historyRetryEligible(cell) {
  if (!cell || typeof cell !== "object") return false;
  return canonicalCellStatus(cell.status) === "failed";
}

/** Counts line text (e.g. "12 results · 12 total cells"). */
export function buildExperimentCountsText(rec) {
  const parts = [];
  if (rec.resultCount > 0) {
    parts.push(rec.resultCount + (rec.resultCount === 1 ? " result" : " results"));
  }
  if (rec.failedCount > 0) {
    parts.push(rec.failedCount + (rec.failedCount === 1 ? " failed" : " failed"));
  }
  if (rec.interruptedCount > 0) {
    parts.push(rec.interruptedCount + (rec.interruptedCount === 1 ? " interrupted" : " interrupted"));
  }
  if (rec.trueCellCount > 0) {
    parts.push(rec.trueCellCount + (rec.trueCellCount === 1 ? " total cell" : " total cells"));
  }
  return parts.join(" \u00b7 ");
}

/** Axis line text (e.g. "Axis X: seed · Axis Y: steps"). */
export function buildExperimentAxisText(rec) {
  const ax = rec && rec.axisLabels ? rec.axisLabels : {};
  const parts = [];
  if (ax.x) parts.push("Axis X: " + ax.x);
  if (ax.y) parts.push("Axis Y: " + ax.y);
  return parts.join(" \u00b7 ");
}

function _row(key, value) {
  if (value == null || value === "") return null;
  return el("div", { class: "comfymodal-studio-history-v2-row" }, [
    el("span", { class: "comfymodal-studio-history-v2-row-key", text: key }),
    el("span", { class: "comfymodal-studio-history-v2-row-value", text: String(value) }),
  ]);
}

function _hideOnError(e) {
  e.currentTarget.style.display = "none";
}

function _previewBadge() {
  return el("span", {
    class: "comfymodal-studio-history-v2-badge comfymodal-studio-history-v2-preview-badge",
    "data-testid": "history-v2-preview-badge",
    text: "Preview",
  });
}

function _cellAssetPlaceholder(asset) {
  return el("div", {
    class: "comfymodal-studio-history-v2-cell-thumb comfymodal-studio-history-v2-cell-empty",
    "data-asset-kind": asset.kind,
  }, [el("span", { text: asset.label })]);
}

// ── Main entry ────────────────────────────────────────────────────────────

export async function renderExperimentDetail(experimentId, repo, callbacks) {
  const cbs = callbacks || {};

  const page = el("div", {
    class: "comfymodal-studio-history-v2-experiment",
    "data-testid": "history-v2-experiment-page",
  });

  // Show a loading placeholder while the record is being fetched.
  page.appendChild(el("div", { class: "comfymodal-studio-history-v2-state", text: "Loading\u2026" }));

  let record = null;
  try {
    record = await repo.getExperiment(experimentId);
  } catch (err) {
    record = null;
  }

  // ── Shared state for the page ──────────────────────────────────────────
  let currentRecord = record;
  let selectedCellKey = null;
  let gridEl = null;
  let gridNoteEl = null;
  let detailPaneEl = null;
  let _activeMenu = null;
  let _outsideHandler = null;

  function closeAnyMenu() {
    if (_activeMenu) {
      _activeMenu.remove();
      _activeMenu = null;
    }
    if (_outsideHandler) {
      document.removeEventListener("mousedown", _outsideHandler);
      _outsideHandler = null;
    }
  }

  function positionMenu(menu, anchor) {
    const r = anchor.getBoundingClientRect();
    menu.style.position = "fixed";
    menu.style.top = (r.bottom + 4) + "px";
    menu.style.left = Math.max(8, r.left) + "px";
  }

  function openCellMenu(anchor, cell) {
    closeAnyMenu();
    const menu = el("div", { class: "comfymodal-studio-history-v2-menu" });
    // Generate Original is deferred in this release: visibly disabled and it
    // never calls repository generation or asset export.
    const item = el("button", {
      class: "comfymodal-studio-history-v2-menu-item",
      "data-testid": "history-v2-cell-generate-original",
      type: "button",
      text: "Generate Original (unavailable)",
      disabled: true,
      title: "Generate Original is not available in this release.",
      onclick: function () { closeAnyMenu(); },
    });
    menu.appendChild(item);
    positionMenu(menu, anchor);
    menu.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeAnyMenu();
    });
    document.body.appendChild(menu);
    _activeMenu = menu;
    _outsideHandler = function onDown(ev) {
      if (!menu.contains(ev.target) && ev.target !== anchor && !anchor.contains(ev.target)) {
        closeAnyMenu();
      }
    };
    document.addEventListener("mousedown", _outsideHandler);
    item.focus();
  }

  function _favStar(rec) {
    const star = el("button", {
      type: "button",
      class: "comfymodal-studio-history-v2-fav",
      "aria-label": rec.favorite ? "Remove from favorites" : "Add to favorites",
      "aria-pressed": rec.favorite ? "true" : "false",
      title: rec.favorite ? "Remove from favorites" : "Add to favorites",
      text: rec.favorite ? "\u2605" : "\u2606",
    });
    star.addEventListener("click", async function () {
      const next = !rec.favorite;
      try {
        await repo.setFavorite(rec.id, next);
        rec.favorite = next;
      } catch (err) { /* keep current state on failure */ }
      star.textContent = rec.favorite ? "\u2605" : "\u2606";
      star.setAttribute("aria-pressed", rec.favorite ? "true" : "false");
      star.setAttribute("aria-label", rec.favorite ? "Remove from favorites" : "Add to favorites");
      if (typeof cbs.onChanged === "function") cbs.onChanged();
    });
    return star;
  }

  function buildNotesSection(rec) {
    const sec = el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Note" }),
    ]);
    const textarea = el("textarea", {
      class: "comfymodal-studio-history-v2-notes",
      "aria-label": "Note for this experiment",
    });
    textarea.value = rec.note || "";
    const statusEl = el("span", { class: "comfymodal-studio-history-v2-action-note" });
    const saveBtn = el("button", {
      class: "comfymodal-secondary-btn",
      type: "button",
      text: "Save note",
      onclick: async function () {
        saveBtn.disabled = true;
        try {
          await repo.setNote(rec.id, textarea.value);
          rec.note = textarea.value;
          statusEl.textContent = "Saved";
        } catch (err) {
          statusEl.textContent = "Save failed";
        }
        saveBtn.disabled = false;
        if (typeof cbs.onChanged === "function") cbs.onChanged();
      },
    });
    const row = el("div", { class: "comfymodal-studio-history-v2-action-row" }, [saveBtn, statusEl]);
    sec.appendChild(textarea);
    sec.appendChild(row);
    return sec;
  }

  // ── Header ─────────────────────────────────────────────────────────────
  function buildCountsLine(rec) {
    const text = buildExperimentCountsText(rec);
    if (!text) return null;
    return el("div", {
      class: "comfymodal-studio-history-v2-experiment-counts",
      "data-testid": "history-v2-experiment-counts",
      text: text,
    });
  }

  function buildAxisLine(rec) {
    const text = buildExperimentAxisText(rec);
    if (!text) return null;
    return el("div", { class: "comfymodal-studio-history-v2-experiment-axis", text: text });
  }

  function buildHeader(rec) {
    const header = el("div", { class: "comfymodal-studio-history-v2-experiment-header" });

    header.appendChild(el("button", {
      class: "comfymodal-secondary-btn comfymodal-studio-history-v2-back",
      type: "button",
      text: "\u2190 Back to history",
      onclick: function () {
        closeAnyMenu();
        if (typeof cbs.onBack === "function") cbs.onBack();
      },
    }));

    header.appendChild(el("div", { class: "comfymodal-studio-history-v2-experiment-title-row" }, [
      el("h2", { class: "comfymodal-studio-history-v2-experiment-title", text: rec.name || rec.id || "Experiment" }),
      _statusChip(rec.status),
      _favStar(rec),
    ]));

    const countsEl = buildCountsLine(rec);
    if (countsEl) header.appendChild(countsEl);
    const axisEl = buildAxisLine(rec);
    if (axisEl) header.appendChild(axisEl);

    const metaParts = [];
    if (rec.workflow) metaParts.push(rec.workflow);
    if (rec.preset) metaParts.push(rec.preset);
    const metaLine = el("div", { class: "comfymodal-studio-history-v2-row" });
    if (metaParts.length > 0) {
      metaLine.appendChild(el("span", { class: "comfymodal-studio-history-v2-row-value", text: metaParts.join(" \u00b7 ") }));
    }
    if (rec.durationMs != null) {
      metaLine.appendChild(el("span", { class: "comfymodal-studio-history-v2-row-value", text: _formatDuration(rec.durationMs) }));
    }
    header.appendChild(metaLine);

    header.appendChild(buildNotesSection(rec));

    // Retry action — experiment-level retry-all is NOT exposed (D5).  The
    // button stays visible for test/legacy compatibility but is disabled and
    // never calls the repository; per-cell Retry on failed cells is the only
    // retry path (repo.retryCell, same cell identity, new attempt).
    const retryNote = el("span", { class: "comfymodal-studio-history-v2-action-note" });
    const retryBtn = el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "history-v2-experiment-retry",
      type: "button",
      text: "Retry experiment",
      disabled: true,
      title: "Experiment-level retry-all is not available. Use the per-cell Retry on failed cells.",
      onclick: function () { retryNote.textContent = "Use per-cell Retry on failed cells."; },
    });
    retryNote.textContent = "Use per-cell Retry on failed cells.";
    const retryRow = el("div", { class: "comfymodal-studio-history-v2-action-row" }, [retryBtn, retryNote]);
    header.appendChild(retryRow);

    // Resume action — only when interrupted/queued cells exist.  Calls the
    // modern resume route once; the controller/reconcile re-reads status.
    const resumeNote = el("span", { class: "comfymodal-studio-history-v2-action-note" });
    const resumeBtn = el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "history-v2-experiment-resume",
      type: "button",
      text: "Resume experiment",
      hidden: !historyResumeEligible(rec),
      onclick: async function () {
        if (resumeBtn.disabled) return;
        resumeBtn.disabled = true;
        resumeBtn.textContent = "Queuing\u2026";
        let resp = null;
        try {
          resp = await repo.resumeExperiment(rec.id);
        } catch (err) {
          resp = { accepted: false, message: (err && err.message) || "Request failed" };
        }
        resumeBtn.disabled = false;
        resumeBtn.textContent = "Resume experiment";
        resumeNote.textContent = resp && resp.message
          ? resp.message
          : (resp && resp.accepted ? "Resume queued" : "Not available yet");
        if (typeof cbs.onChanged === "function") cbs.onChanged();
      },
    });
    const resumeRow = el("div", { class: "comfymodal-studio-history-v2-action-row" }, [resumeBtn, resumeNote]);
    header.appendChild(resumeRow);

    return header;
  }

  // ── Cell grid ──────────────────────────────────────────────────────────
  function _matrixLayout(cells, axisLabels) {
    if (!cells || cells.length === 0) return null;
    if (!axisLabels || !axisLabels.x || !axisLabels.y) return null;
    let allKnown = true;
    cells.forEach(function (c) {
      if (!c || !c.axis || c.axis.x === "" || c.axis.y === "") allKnown = false;
    });
    if (!allKnown) return null;
    const cols = [];
    const rows = [];
    cells.forEach(function (c) {
      if (cols.indexOf(c.axis.x) === -1) cols.push(c.axis.x);
      if (rows.indexOf(c.axis.y) === -1) rows.push(c.axis.y);
    });
    if (cols.length === 0 || rows.length === 0) return null;
    return { cols: cols, rows: rows };
  }

  function cellAxisLabel(cell, index) {
    const axis = cell.axis || {};
    const ax = (currentRecord && currentRecord.axisLabels) || {};
    if (ax.x && axis.x !== "") return ax.x + " " + axis.x;
    if (ax.y && axis.y !== "") return ax.y + " " + axis.y;
    return "Cell " + historyCellIdentity(cell, index);
  }

  function buildCellTile(cell, index, rec) {
    const key = historyCellIdentity(cell, index);
    const asset = selectExperimentCellAsset(cell);
    const hasImage = !!asset.url;
    const axisLabel = cellAxisLabel(cell, index);
    const selected = selectedCellKey === key;
    const wf = cellWorkflowMeta(cell, rec);
    const wfParts = [wf.workflow, wf.version, wf.preset].filter(Boolean);
    const attemptCount = historyCellAttemptCount(cell);
    const retryEligible = historyRetryEligible(cell);

    const retryNote = el("span", { class: "comfymodal-studio-history-v2-action-note" });
    const retryBtn = el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "history-v2-cell-retry-" + key,
      type: "button",
      text: "Retry",
      hidden: !retryEligible,
      onclick: async function () {
        if (retryBtn.disabled) return;
        retryBtn.disabled = true;
        retryBtn.textContent = "Queuing\u2026";
        let resp = null;
        try {
          resp = await repo.retryCell(rec.id, key);
        } catch (err) {
          resp = { accepted: false, message: (err && err.message) || "Request failed" };
        }
        retryBtn.disabled = false;
        retryBtn.textContent = "Retry";
        retryNote.textContent = resp && resp.message
          ? resp.message
          : (resp && resp.accepted ? "Retry queued" : "Not available yet");
        if (typeof cbs.onChanged === "function") cbs.onChanged();
      },
    });

    return el("div", {
      class: "comfymodal-studio-history-v2-cell" + (selected ? " selected" : ""),
      "data-testid": "history-v2-experiment-cell",
      "data-key": key,
      "data-cell-id": key,
      role: "button",
      tabindex: "0",
      "aria-pressed": selected ? "true" : "false",
      "aria-label": axisLabel + ", " + experimentStatusLabel(cell.status),
      onclick: function () { selectCell(key); },
      onkeydown: function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectCell(key);
        }
      },
    }, [
      hasImage
        ? (function () {
          const thumb = el("div", { class: "comfymodal-studio-history-v2-cell-thumb" }, [
            el("img", {
              class: "comfymodal-studio-history-v2-thumb-img",
              src: asset.url,
              alt: axisLabel,
              loading: "lazy",
              onerror: function (e) {
                e.currentTarget.style.display = "none";
                if (e.currentTarget.parentNode) e.currentTarget.parentNode.appendChild(_cellAssetPlaceholder(asset));
              },
            }),
          ]);
          if (asset.kind === "preview") thumb.appendChild(_previewBadge());
          return thumb;
        }())
        : _cellAssetPlaceholder(asset),
      _statusChip(cell.status),
      el("div", { class: "comfymodal-studio-history-v2-cell-axis", text: axisLabel }),
      wfParts.length > 0
        ? el("div", {
            class: "comfymodal-studio-history-v2-cell-wfmeta",
            "data-testid": "history-v2-cell-workflow-meta-" + key,
            text: wfParts.join(" \u00b7 "),
          })
        : null,
      attemptCount > 0
        ? el("div", {
            class: "comfymodal-studio-history-v2-cell-attempts",
            "data-testid": "history-v2-cell-attempts-" + key,
            text: attemptCount + (attemptCount === 1 ? " attempt" : " attempts"),
          })
        : null,
      el("div", { class: "comfymodal-studio-history-v2-cell-actions" }, [retryBtn, retryNote]),
      el("button", {
        class: "comfymodal-studio-history-v2-menu-btn",
        type: "button",
        "aria-label": "Cell " + key + " actions",
        title: "Cell actions",
        text: "\u22ef",
        onclick: function (e) {
          e.stopPropagation();
          openCellMenu(e.currentTarget, cell);
        },
      }),
    ]);
  }

  function buildGrid(rec) {
    const cells = Array.isArray(rec.cells) ? rec.cells : [];
    const axisLabels = rec.axisLabels || {};
    const matrix = _matrixLayout(cells, axisLabels);

    const grid = el("div", {
      class: "comfymodal-studio-history-v2-experiment-grid" + (matrix ? " matrix" : ""),
      "data-testid": "history-v2-experiment-grid",
    });
    if (matrix) grid.style.setProperty("--matrix-cols", String(matrix.cols.length));

    cells.forEach(function (cell, index) {
      if (!cell) return;
      grid.appendChild(buildCellTile(cell, index, rec));
    });

    if (matrix) {
      const keyToAxis = {};
      cells.forEach(function (c, i) {
        if (c) keyToAxis[historyCellIdentity(c, i)] = c.axis;
      });
      grid.querySelectorAll(".comfymodal-studio-history-v2-cell").forEach(function (tile) {
        const axis = keyToAxis[tile.getAttribute("data-key")] || {};
        const rowIdx = matrix.rows.indexOf(axis.y);
        const colIdx = matrix.cols.indexOf(axis.x);
        if (rowIdx >= 0 && colIdx >= 0) {
          tile.style.gridRow = String(rowIdx + 1);
          tile.style.gridColumn = String(colIdx + 1);
        }
      });
    }

    return grid;
  }

  // ── Selected-cell detail pane ──────────────────────────────────────────
  function buildCellDetail(cell, rec) {
    const key = historyCellIdentity(cell, 0);
    const pane = el("div", { class: "comfymodal-studio-history-v2-cell-detail", "data-testid": "history-v2-cell-detail" });

    pane.appendChild(_row("Cell", key));
    pane.appendChild(el("div", { class: "comfymodal-studio-history-v2-row" }, [
      el("span", { class: "comfymodal-studio-history-v2-row-key", text: "Status" }),
      _statusChip(cell.status),
    ]));
    if (cell.durationMs != null) {
      pane.appendChild(_row("Duration", _formatDuration(cell.durationMs)));
    }
    const wf = cellWorkflowMeta(cell, rec);
    if (wf.workflow) pane.appendChild(_row("Workflow", wf.workflow));
    if (wf.version) pane.appendChild(_row("Version", wf.version));
    if (wf.preset) pane.appendChild(_row("Preset", wf.preset));
    const attemptCount = historyCellAttemptCount(cell);
    if (attemptCount > 0) {
      pane.appendChild(_row("Attempts", String(attemptCount)));
      if (Array.isArray(cell.attempts) && cell.attempts.length > 0) {
        const attemptsList = el("div", { class: "comfymodal-studio-history-v2-cell-attempt-list", "data-testid": "history-v2-cell-attempt-list" });
        cell.attempts.forEach(function (a) {
          const line = el("div", { class: "comfymodal-studio-history-v2-cell-attempt-row" });
          const purpose = historyAttemptPurposeLabel(a && (a.mode || a.purpose));
          const label = a && a.status ? experimentStatusLabel(a.status) : "Attempt";
          const runId = a && (a.run_id || a.runId) ? " \u00b7 " + String(a.run_id || a.runId) : "";
          line.textContent = purpose + " \u00b7 " + label + runId;
          if (a && a.error) {
            const errLine = el("div", { class: "comfymodal-studio-history-v2-attempt-error", text: String(a.error) });
            line.appendChild(errLine);
          }
          attemptsList.appendChild(line);
        });
        pane.appendChild(attemptsList);
      }
    }
    if (cell.error) {
      pane.appendChild(el("div", { class: "comfymodal-studio-history-v2-attempt-error", text: String(cell.error) }));
    }

    const avail = [];
    const displayed = selectDetailAsset(cell);
    if (displayed.kind === "preview") avail.push("Preview available");
    else if (displayed.kind === "thumbnail") avail.push("Thumbnail available");
    else avail.push("No preview");
    if (cell.originalUrl) avail.push("Original available");
    else if (cell.originalFailed) avail.push("Original failed");
    else avail.push("No original");
    pane.appendChild(_row("Outputs", avail.join(" \u00b7 ")));

    // Per-cell favorite (local toggle — the repository has no per-cell setter).
    const favBtn = el("button", {
      type: "button",
      class: "comfymodal-studio-history-v2-fav",
      "aria-label": cell.favorite ? "Remove from favorites" : "Add to favorites",
      "aria-pressed": cell.favorite ? "true" : "false",
      title: cell.favorite ? "Remove from favorites" : "Add to favorites",
      text: cell.favorite ? "\u2605" : "\u2606",
    });
    favBtn.addEventListener("click", function () {
      cell.favorite = !cell.favorite;
      favBtn.textContent = cell.favorite ? "\u2605" : "\u2606";
      favBtn.setAttribute("aria-pressed", cell.favorite ? "true" : "false");
      favBtn.setAttribute("aria-label", cell.favorite ? "Remove from favorites" : "Add to favorites");
    });

    const note = el("span", { class: "comfymodal-studio-history-v2-action-note" });

    // Per-cell Retry — only for failed cells; preserves position and old
    // attempts (the repository appends a new attempt under the same cell).
    const retryBtn = el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "history-v2-cell-detail-retry-" + key,
      type: "button",
      text: "Retry cell",
      hidden: !historyRetryEligible(cell),
      onclick: async function () {
        if (retryBtn.disabled) return;
        retryBtn.disabled = true;
        retryBtn.textContent = "Queuing\u2026";
        let resp = null;
        try {
          resp = await repo.retryCell(rec.id, key);
        } catch (err) {
          resp = { accepted: false, message: (err && err.message) || "Request failed" };
        }
        retryBtn.disabled = false;
        retryBtn.textContent = "Retry cell";
        note.textContent = resp && resp.message
          ? resp.message
          : (resp && resp.accepted ? "Retry queued" : "Not available yet");
        if (typeof cbs.onChanged === "function") cbs.onChanged();
      },
    });

    // Generate Original is deferred in this release: visibly disabled and it
    // never calls repository generation or asset export.
    const genBtn = el("button", {
      class: "comfymodal-secondary-btn",
      type: "button",
      text: "Generate Original (unavailable)",
      disabled: true,
      title: "Generate Original is not available in this release.",
    });

    pane.appendChild(el("div", { class: "comfymodal-studio-history-v2-action-row" }, [favBtn, retryBtn, genBtn, note]));
    return pane;
  }

  function renderCellDetail() {
    if (!detailPaneEl) return;
    while (detailPaneEl.firstChild) detailPaneEl.removeChild(detailPaneEl.firstChild);
    if (!currentRecord) {
      detailPaneEl.appendChild(el("div", { class: "comfymodal-studio-history-v2-cell-detail-hint", text: "Select a cell to see details" }));
      return;
    }
    const cells = Array.isArray(currentRecord.cells) ? currentRecord.cells : [];
    let cell = null;
    for (let i = 0; i < cells.length; i++) {
      if (cells[i] && historyCellIdentity(cells[i], i) === selectedCellKey) { cell = cells[i]; break; }
    }
    if (!cell) {
      detailPaneEl.appendChild(el("div", { class: "comfymodal-studio-history-v2-cell-detail-hint", text: "Select a cell to see details" }));
      return;
    }
    detailPaneEl.appendChild(buildCellDetail(cell, currentRecord));
  }

  function selectCell(key) {
    selectedCellKey = key;
    if (gridEl) {
      gridEl.querySelectorAll(".comfymodal-studio-history-v2-cell").forEach(function (tile) {
        const sel = tile.getAttribute("data-key") === key;
        tile.classList.toggle("selected", sel);
        tile.setAttribute("aria-pressed", sel ? "true" : "false");
      });
    }
    renderCellDetail();
  }

  function buildBody(rec) {
    const body = el("div", { class: "comfymodal-studio-history-v2-experiment-body" });
    gridEl = buildGrid(rec);
    body.appendChild(gridEl);
    gridNoteEl = el("div", { class: "comfymodal-studio-history-v2-action-note", "aria-live": "polite" });
    body.appendChild(gridNoteEl);
    detailPaneEl = el("div", { class: "comfymodal-studio-history-v2-cell-detail-wrap" });
    body.appendChild(detailPaneEl);
    renderCellDetail();
    return body;
  }

  // ── Not-found / normal mount ───────────────────────────────────────────
  function _isNotFound(rec) {
    if (!rec || !rec.id) return true;
    return Array.isArray(rec.errors)
      && rec.errors.length > 0
      && !(Array.isArray(rec.cells) && rec.cells.length > 0);
  }

  while (page.firstChild) page.removeChild(page.firstChild);

  if (_isNotFound(record)) {
    page.appendChild(el("div", { class: "comfymodal-studio-history-v2-state" }, [
      el("p", { text: "Experiment not found" }),
      el("button", {
        class: "comfymodal-secondary-btn",
        type: "button",
        text: "\u2190 Back to history",
        onclick: function () {
          if (typeof cbs.onBack === "function") cbs.onBack();
        },
      }),
    ]));
    return page;
  }

  page.appendChild(buildHeader(record));
  page.appendChild(buildBody(record));
  return page;
}
