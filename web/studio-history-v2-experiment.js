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
import { renderLoadingState } from "./studio-loading.js";
import { _formatDuration } from "./studio-run-normalizer.js";
import {
  buildAddToCompareItem,
  shortIdTail,
  startCompare,
} from "./studio-image-compare.js";
import {
  deriveOriginalActionState,
  deriveRetryActionLabel,
  generateOriginalEligibility,
  isTerminalAttemptStatus,
  selectDetailAsset,
  selectFeedAsset,
} from "./history-v2-repository.js";
import { buildManagedAssetDownloadButton } from "./history-v2-browser-download.js";
import { buildConfiguredExportButton, exportResultNote } from "./history-v2-export.js";

// ── Constants / helpers ───────────────────────────────────────────────────

const CELL_DOWNLOAD_NOTE_TESTID = "history-v2-cell-download-note";
const CELL_EXPORT_NOTE_TESTID = "history-v2-cell-export-note";

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

// Shared chip tones (I3 taxonomy): canonical cell STATUS → data-tone.
// Legacy status-* classes stay verbatim; status meaning never changes.
// Unknown passthrough keys render the neutral/meta tone.
const STATUS_TONES = {
  completed: "ok",
  completed_with_failures: "warn",
  failed: "error",
  canceled: "neutral",
  interrupted: "warn",
  running: "running",
  queued: "running",
};

function _statusChip(status) {
  const key = canonicalCellStatus(status);
  const label = experimentStatusLabel(status);
  return el("span", {
    class: "comfymodal-studio-history-v2-chip status-" + key + " cm-chip",
    "data-tone": STATUS_TONES[key] || "neutral",
    text: label,
  });
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

/**
 * Experiment Cancel eligibility, derived from DURABLE cell state using the
 * backend's own truth table (experiment_modern_routes._handle_cancel):
 * cancel applies exactly when at least one cell is queued or running.  An
 * all-terminal aggregate (completed / completed_with_failures / failed /
 * canceled / interrupted-only) is refused by the backend (409
 * EXPERIMENT_TERMINAL, or idempotent 200 when every cell is already
 * canceled), so no misleading enabled Cancel is offered for those states.
 */
export function historyExperimentCancelEligible(rec) {
  if (!rec) return false;
  const cells = Array.isArray(rec.cells) ? rec.cells : [];
  let eligible = false;
  cells.forEach(function (c) {
    const s = canonicalCellStatus(c && c.status);
    if (s === "queued" || s === "running") eligible = true;
  });
  return eligible;
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
  page.appendChild(renderLoadingState({
    label: "Loading experiment\u2026",
    size: "page",
    testid: "history-v2-experiment-detail-loading",
  }));

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

  // ── Generate / Retry Original for a cell (E4C/E4D) ──────────────────────
  //
  // Uses the CELL'S OWN generation_id and the SAME frozen Generation-scoped
  // routes as the detail page: Generate Original posts /original via
  // repo.generateOriginalForCell; Retry Original posts /original/retry via
  // repo.retryOriginalForCell.  Never the cell index, never a legacy
  // generation endpoint, no browser fanout, no second Generation.  The
  // retained Preview/thumbnail is never replaced.

  const _inFlightOriginal = Object.create(null);
  let _cellPollTimer = null;

  function _repoModeInfo() {
    try {
      return typeof repo.getModeInfo === "function" ? repo.getModeInfo() : null;
    } catch (err) {
      return null;
    }
  }

  function _cellGenerationId(cell) {
    return String((cell && (cell.generationId || cell.generation_id)) || "");
  }

  function _startCellOriginalPolling() {
    if (_cellPollTimer) return;
    let ticks = 0;
    const tick = async function () {
      _cellPollTimer = null;
      if (typeof page.isConnected !== "undefined" && !page.isConnected) return;
      ticks++;
      let fresh = null;
      try {
        fresh = await repo.getExperiment(experimentId);
      } catch (err) {
        fresh = null;
      }
      if (fresh && !_isNotFound(fresh)) {
        let anyActive = false;
        const cells = Array.isArray(fresh.cells) ? fresh.cells : [];
        cells.forEach(function (c) {
          const st = deriveOriginalActionState(c);
          if (st.latestAttempt && !isTerminalAttemptStatus(st.latestAttempt.status)) anyActive = true;
        });
        _rerenderPage(fresh);
        if (!anyActive || ticks >= 150) {
          if (gridNoteEl) gridNoteEl.textContent = "Original attempt finished.";
          if (typeof cbs.onChanged === "function") cbs.onChanged();
          return;
        }
      } else if (ticks >= 150) {
        return;
      }
      _cellPollTimer = setTimeout(tick, 2000);
    };
    _cellPollTimer = setTimeout(tick, 2000);
  }

  // Shared runner for both cell Original actions: one per-generation
  // in-flight guard, one POST, truthful refusals, durable-state poll after.
  async function _postCellOriginalAction(genId, send, pendingLabel, actionLabel) {
    if (!genId || _inFlightOriginal[genId]) return;
    _inFlightOriginal[genId] = true;
    closeAnyMenu();
    if (gridNoteEl) gridNoteEl.textContent = pendingLabel;
    let resp = null;
    let errMsg = "";
    try {
      resp = await send();
    } catch (err) {
      errMsg = err && err.message ? err.message : "Request failed";
    }
    delete _inFlightOriginal[genId];
    if (errMsg) {
      if (gridNoteEl) gridNoteEl.textContent = actionLabel + " failed: " + errMsg + " \u2014 preview retained.";
      return;
    }
    if (resp && resp.accepted === false) {
      const outcome = resp.outcome ? String(resp.outcome) : "";
      if (outcome === "busy") {
        if (gridNoteEl) gridNoteEl.textContent = "Generation is busy \u2014 preview retained.";
      } else if (outcome === "irreproducible" || resp.errorCode === "irreproducible") {
        if (gridNoteEl) {
          gridNoteEl.textContent = "This saved generation does not contain the exact immutable execution data required to generate an Original.";
        }
      } else if (outcome === "retry_required") {
        // Machine-readable state transition from ordinary /original:
        // failed-only Original.  Never auto-retry and never loop back into
        // /original — the durable failed cell state stands; Retry Original
        // is the explicit next user action.
        if (gridNoteEl) {
          gridNoteEl.textContent = resp.errorMessage || resp.message
            || "Original failed \u2014 use Retry Original to try again.";
        }
      } else {
        if (gridNoteEl) {
          gridNoteEl.textContent = resp.errorMessage || resp.message
            || actionLabel + " was not accepted \u2014 preview retained.";
        }
      }
      return;
    }
    // accepted: new attempt or reused existing run — poll durable state.
    _startCellOriginalPolling();
  }

  function _runCellGenerateOriginal(genId, rerender) {
    return _postCellOriginalAction(genId, function () {
      return repo.generateOriginalForCell(genId, rerender === true ? { rerender: true } : undefined);
    }, "Generating Original\u2026", "Generate Original");
  }

  // E4D: explicit failed-Attempt retry for a cell — the dedicated
  // /original/retry route under the SAME generation identity, no rerender
  // flag, exactly one POST per click.
  function _runCellRetryOriginal(genId) {
    return _postCellOriginalAction(genId, function () {
      return repo.retryOriginalForCell(genId);
    }, "Retrying Original\u2026", "Retry Original");
  }

  // ── Configured-folder Export for a cell (F9 route / F10 frontend) ───────
  //
  // Uses the CELL'S OWN projected Preview/Original Asset IDs and the SAME
  // frozen asset-scoped route as the Single detail: one bodyless POST
  // /history-v2/assets/{asset_id}/export per explicit click.  No
  // Experiment-specific backend route, no browser fanout, no local export-
  // state mutation — the durable Experiment refetch afterwards is the sole
  // authority for exported / missing / failed.

  const _exportInFlightByAsset = Object.create(null);

  async function _runCellExport(assetId) {
    const id = assetId == null ? "" : String(assetId);
    if (!id || _exportInFlightByAsset[id]) return null;
    _exportInFlightByAsset[id] = true;
    let result = null;
    try {
      result = typeof repo.exportAsset === "function"
        ? await repo.exportAsset(id)
        : { ok: false, reason: "unavailable", message: "Export is not available in this repository mode" };
    } catch (err) {
      result = {
        ok: false,
        reason: "network_error",
        message: err && err.message ? err.message : "request failed",
      };
    }
    delete _exportInFlightByAsset[id];
    if (typeof page.isConnected !== "undefined" && !page.isConnected) return result;
    // Immediate truthful response while the durable refetch runs…
    _paintCellExportNote(exportResultNote(result));
    let fresh = null;
    try {
      fresh = await repo.getExperiment(experimentId);
    } catch (err) {
      fresh = null;
    }
    if (typeof page.isConnected !== "undefined" && !page.isConnected) return result;
    if (fresh && !_isNotFound(fresh)) {
      _rerenderPage(fresh);
      _paintCellExportNote(exportResultNote(result));
      if (typeof cbs.onChanged === "function") cbs.onChanged();
    }
    return result;
  }

  function _paintCellExportNote(text) {
    try {
      const noteEl = page.querySelector('[data-testid="' + CELL_EXPORT_NOTE_TESTID + '"]');
      if (noteEl) noteEl.textContent = text;
    } catch (err) { /* detached page — nothing to paint */ }
  }

  /**
   * Stateful Generate Original control for one cell.  variant "menu" renders
   * a menu item; variant "pane" renders a secondary button in the detail
   * pane.  Both share the same state derivation from durable backend data.
   */
  function buildCellOriginalAction(cell, rec, variant) {
    const key = historyCellIdentity(cell, 0);
    const genId = _cellGenerationId(cell);
    const st = deriveOriginalActionState(cell);
    const eligibility = generateOriginalEligibility({ id: genId }, _repoModeInfo());
    const testid = variant === "menu"
      ? "history-v2-cell-generate-original"
      : "history-v2-cell-detail-generate-original-" + key;

    let label = "";
    let disabled = false;
    let title = "";
    let rerender = false;
    // E4D: "generate" (ordinary /original, rerender only for Generate Again)
    // vs "retry" (dedicated /original/retry for a failed latest Attempt).
    let action = "generate";

    if (!eligibility.eligible) {
      label = "Generate Original unavailable";
      disabled = true;
      title = eligibility.message;
    } else if (st.phase === "active") {
      label = "Generating Original\u2026";
      disabled = true;
    } else if (st.phase === "success") {
      label = "Generate Again";
      rerender = true;
      title = "Rerun the frozen execution plan as a new Original attempt (rerender).";
    } else if (st.phase === "failed") {
      // F6 truthful naming: same durable predicate as the Single detail —
      // plain failed run vs explicit Original derivative failure.  Both
      // dispatch the dedicated /original/retry route.
      label = deriveRetryActionLabel(cell);
      action = "retry";
      title = "Creates a new attempt on the backend under the same generation.";
    } else if (st.busyGeneration) {
      label = "Generate Original";
      disabled = true;
      title = "Generation busy \u2014 wait for the current run to finish.";
    } else {
      label = "Generate Original";
    }

    const attrs = {
      class: variant === "menu"
        ? "comfymodal-studio-history-v2-menu-item"
        : "comfymodal-secondary-btn",
      "data-testid": testid,
      type: "button",
      text: label,
      disabled: disabled || !!_inFlightOriginal[genId],
    };
    if (title) attrs.title = title;
    attrs.onclick = function () {
      closeAnyMenu();
      if (action === "retry") _runCellRetryOriginal(genId);
      else _runCellGenerateOriginal(genId, rerender);
    };
    return el("button", attrs);
  }

  function openCellMenu(anchor, cell) {
    closeAnyMenu();
    const menu = el("div", { class: "comfymodal-studio-history-v2-menu" });
    menu.appendChild(buildCellOriginalAction(cell, currentRecord, "menu"));
    // While a compare session is active, an eligible cell image fills slot
    // B (further picks truthfully replace B).
    const menuAsset = selectExperimentCellAsset(cell);
    if (menuAsset.url && currentRecord) {
      const compareItem = buildAddToCompareItem({
        descriptor: {
          url: menuAsset.url,
          label: cellAxisLabel(cell, 0),
          kind: menuAsset.kind,
          meta: (currentRecord.name || "Experiment") + " \u00b7 " + shortIdTail(_cellGenerationId(cell)),
          alt: cellAxisLabel(cell, 0),
        },
        testId: "history-v2-cell-add-to-compare-" + historyCellIdentity(cell, 0),
        className: "comfymodal-studio-history-v2-menu-item cm-compare-menu-item",
      });
      if (compareItem) menu.appendChild(compareItem);
    }
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
    // Focus the first actionable menu item: the menu is a plain container of
    // buttons, so the first enabled one receives focus (existing UI
    // convention — native button semantics, Escape already closes via the
    // menu keydown handler).  Never an unbound name.
    const firstMenuItem = menu.querySelector("button:not([disabled])");
    if (firstMenuItem) firstMenuItem.focus();
  }

  function _favStar(rec) {
    const star = el("button", {
      type: "button",
      class: "comfymodal-studio-history-v2-fav",
      "aria-label": rec.favorite ? "Remove experiment from favorites" : "Add experiment to favorites",
      "aria-pressed": rec.favorite ? "true" : "false",
      title: rec.favorite ? "Remove experiment from favorites" : "Add experiment to favorites",
      text: rec.favorite ? "\u2605" : "\u2606",
    });
    star.addEventListener("click", async function () {
      const next = !rec.favorite;
      try {
        await repo.setFavorite(rec.id, next, { kind: "experiment" });
        rec.favorite = next;
      } catch (err) { /* keep current state on failure */ }
      star.textContent = rec.favorite ? "\u2605" : "\u2606";
      star.setAttribute("aria-pressed", rec.favorite ? "true" : "false");
      star.setAttribute("aria-label", rec.favorite ? "Remove experiment from favorites" : "Add experiment to favorites");
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
          await repo.setNote(rec.id, textarea.value, { kind: "experiment" });
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

    // Cancel action — parity with the live Playground Experiment controller
    // and the frozen backend route (POST .../experiments/{id}/cancel via
    // repo.cancelExperiment; no second cancellation concept).  Eligibility
    // follows durable cell truth (historyExperimentCancelEligible): an
    // all-terminal aggregate never shows a Cancel that can only fail.  No
    // optimistic canceled state: one guarded POST, then the page re-renders
    // from the refetched durable record so the UI only ever shows server
    // truth — a running-cell refusal (503 CANCELLATION_UNAVAILABLE) keeps
    // the experiment truthfully running with a concise error note.
    let cancelInFlight = false;
    const cancelBtn = el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "history-v2-experiment-cancel",
      type: "button",
      text: "Cancel experiment",
      hidden: !historyExperimentCancelEligible(rec),
      onclick: async function () {
        if (cancelBtn.disabled || cancelInFlight) return;
        cancelInFlight = true;
        cancelBtn.disabled = true;
        cancelBtn.textContent = "Canceling\u2026";
        let resp = null;
        let errMsg = "";
        try {
          resp = await repo.cancelExperiment(rec.id);
        } catch (err) {
          errMsg = err && err.message ? err.message : "Request failed";
        }
        // Render server truth: refetch the durable record before repainting.
        let fresh = null;
        try {
          fresh = await repo.getExperiment(experimentId);
        } catch (err) {
          fresh = null;
        }
        cancelInFlight = false;
        const rerendered = !!(fresh && !_isNotFound(fresh));
        if (rerendered) {
          _rerenderPage(fresh);
        } else {
          // Refetch unavailable: recover the control without inventing state.
          cancelBtn.disabled = false;
          cancelBtn.textContent = "Cancel experiment";
        }
        if (errMsg) {
          _paintCancelNote("Cancel failed: " + errMsg);
        } else if (resp && resp.accepted === false) {
          _paintCancelNote(
            resp.errorCode === "CANCELLATION_UNAVAILABLE"
              ? (resp.message || "Running-cell cancellation is unavailable \u2014 running cells remain durable.")
              : (resp.message || "Cancel was not accepted.")
          );
        }
        if (typeof cbs.onChanged === "function") cbs.onChanged();
      },
    });
    const cancelRow = el("div", { class: "comfymodal-studio-history-v2-action-row" }, [
      cancelBtn,
      el("span", {
        class: "comfymodal-studio-history-v2-action-note",
        "data-testid": "history-v2-experiment-cancel-note",
      }),
    ]);
    header.appendChild(cancelRow);

    return header;
  }

  // Cancel status text lands on the CURRENT note element — after a durable
  // refresh the page was rebuilt, so always resolve it from the live DOM.
  function _paintCancelNote(text) {
    const noteEl = page.querySelector('[data-testid="history-v2-experiment-cancel-note"]');
    if (noteEl) noteEl.textContent = text;
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

    // Per-cell Browser Download (F3): Generation-backed parity with the
    // generation detail — Download Preview and Download Original are distinct
    // explicit actions over the CELL'S OWN projected URLs (its Generation's
    // logical output).  One click = one managed-asset GET; no Experiment-
    // specific backend, no legacy Save route, no export state, no browser
    // fanout.  A Thumbnail-only cell downloads truthfully labeled Thumbnail
    // bytes; a failed Original without a retained winner offers no download.
    const genIdForDl = _cellGenerationId(cell);
    const dlMeta = {
      workflow: rec.workflow || "",
      generationId: genIdForDl,
      seed: "",
      outputIndex: 0,
    };
    const dlRow = el("div", { class: "comfymodal-studio-history-v2-action-row" });
    const previewDownload = buildManagedAssetDownloadButton({
      url: cell.previewUrl || cell.thumbUrl || "",
      variant: cell.previewUrl ? "preview" : "thumbnail",
      className: "comfymodal-secondary-btn",
      testId: "history-v2-cell-download-" + (cell.previewUrl ? "preview" : "thumbnail") + "-" + key,
      filenameMeta: dlMeta,
      noteTestId: CELL_DOWNLOAD_NOTE_TESTID,
    });
    if (previewDownload) dlRow.appendChild(previewDownload);
    const originalDownload = buildManagedAssetDownloadButton({
      url: cell.originalUrl && !cell.originalFailed ? cell.originalUrl : "",
      variant: "original",
      className: "comfymodal-secondary-btn",
      testId: "history-v2-cell-download-original-" + key,
      filenameMeta: dlMeta,
      noteTestId: CELL_DOWNLOAD_NOTE_TESTID,
    });
    if (originalDownload) dlRow.appendChild(originalDownload);
    if (dlRow.children.length > 0) pane.appendChild(dlRow);

    // Per-cell configured-folder Export (F10): Generation-backed parity with
    // the Single detail — Export Preview / Export Original (plus Export
    // again / Retry export) over the CELL'S OWN projected Asset IDs.  A
    // distinct action family from Browser Download; one click = one asset
    // export POST; absent variants render no control.
    const exportRow = el("div", { class: "comfymodal-studio-history-v2-action-row" });
    const cellPreviewExport = buildConfiguredExportButton({
      assetId: cell.previewAssetId,
      exportState: cell.previewExportState,
      variant: "preview",
      className: "comfymodal-secondary-btn",
      testId: "history-v2-cell-export-preview-" + key,
      noteTestId: CELL_EXPORT_NOTE_TESTID,
      onExport: function () { return _runCellExport(cell.previewAssetId); },
    });
    if (cellPreviewExport) exportRow.appendChild(cellPreviewExport);
    const cellOriginalExport = buildConfiguredExportButton({
      assetId: cell.originalAssetId,
      exportState: cell.originalExportState,
      variant: "original",
      className: "comfymodal-secondary-btn",
      testId: "history-v2-cell-export-original-" + key,
      noteTestId: CELL_EXPORT_NOTE_TESTID,
      onExport: function () { return _runCellExport(cell.originalAssetId); },
    });
    if (cellOriginalExport) exportRow.appendChild(cellOriginalExport);
    if (exportRow.children.length > 0) pane.appendChild(exportRow);

    // Per-cell favorite — CANONICAL OWNERSHIP: a cell's favorite IS the
    // favorite of its associated Generation.  The star drives the SAME
    // Generation-scoped favorite route as the feed/detail stars via the
    // cell's generationId, then refreshes from durable Experiment detail so
    // the projection reflects server truth.  No per-cell storage, no
    // local-only toggle, no propagation into the whole-Experiment favorite.
    const genId = _cellGenerationId(cell);
    const favNote = el("span", { class: "comfymodal-studio-history-v2-action-note" });
    // Distinguishable accessible names (I1 §3.1): every visible cell star
    // carries its cell context (axis label, e.g. "seed 1"), since the grid
    // renders one favorite control per cell simultaneously.
    const cellCtx = cellAxisLabel(cell, 0);
    function _cellFavoriteName(value) {
      return (value ? "Remove generation for " : "Add generation for ")
        + cellCtx
        + (value ? " from favorites" : " to favorites");
    }
    function _paintFav(btn, value) {
      btn.textContent = value ? "\u2605" : "\u2606";
      btn.setAttribute("aria-pressed", value ? "true" : "false");
      btn.setAttribute("aria-label", _cellFavoriteName(value));
      btn.title = _cellFavoriteName(value);
    }
    const favBtn = el("button", {
      type: "button",
      class: "comfymodal-studio-history-v2-fav",
      "data-testid": "history-v2-cell-favorite",
      "aria-label": _cellFavoriteName(!!cell.favorite),
      "aria-pressed": cell.favorite ? "true" : "false",
      title: genId
        ? _cellFavoriteName(!!cell.favorite)
        : "Favorite unavailable \u2014 no Generation identity for this cell",
      text: cell.favorite ? "\u2605" : "\u2606",
      disabled: !genId,
    });
    favBtn.addEventListener("click", async function () {
      if (!genId || favBtn.disabled) return;
      const prior = !!cell.favorite;
      const next = !prior;
      favBtn.disabled = true;
      favNote.textContent = "";
      try {
        await repo.setFavorite(genId, next);
      } catch (err) {
        // Rejected write: nothing is persisted locally — restore the prior
        // durable state and surface a bounded truthful error.
        _paintFav(favBtn, prior);
        favNote.textContent = "Favorite failed";
        favBtn.disabled = false;
        return;
      }
      // Acknowledged → refresh through the existing Experiment detail flow
      // (same durable refetch the Original poll loop uses); onChanged keeps
      // the feed's Generation favorite semantics consistent everywhere.
      let fresh = null;
      try {
        fresh = await repo.getExperiment(experimentId);
      } catch (err) {
        fresh = null;
      }
      if (fresh && !_isNotFound(fresh)) {
        _rerenderPage(fresh);
      } else {
        // Detail refetch unavailable: paint the acknowledged value on the
        // current DOM without inventing durable state.
        _paintFav(favBtn, next);
        favBtn.disabled = false;
      }
      if (typeof cbs.onChanged === "function") cbs.onChanged();
      const newStar = detailPaneEl
        ? detailPaneEl.querySelector('[data-testid="history-v2-cell-favorite"]')
        : null;
      if (newStar) newStar.focus();
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

    // Generate Original shares the cell-menu action: same generation_id,
    // same frozen route, same state derivation.
    const genBtn = buildCellOriginalAction(cell, rec, "pane");

    // Lightweight A/B compare entry (I5): client-only transient session
    // over the cell's EXISTING projected image. No scheduler mutation, no
    // Experiment authority change, no Experiment-specific compare store.
    const cellDisplayed = selectDetailAsset(cell);
    let cellCompareBtn = null;
    if (cellDisplayed.url) {
      const cellDesc = {
        url: cellDisplayed.url,
        label: cellAxisLabel(cell, 0),
        kind: cellDisplayed.kind,
        meta: (rec && rec.name ? rec.name : "Experiment") + " \u00b7 " + shortIdTail(_cellGenerationId(cell)),
        alt: cellAxisLabel(cell, 0),
      };
      cellCompareBtn = el("button", {
        class: "comfymodal-secondary-btn",
        "data-testid": "history-v2-cell-detail-compare-" + key,
        type: "button",
        text: "Compare",
        title: "Compare this cell image with another reachable output (client-side only)",
        onclick: function () {
          startCompare({ descriptor: cellDesc, invoker: document.activeElement });
        },
      });
      const addB = buildAddToCompareItem({
        descriptor: cellDesc,
        testId: "history-v2-cell-detail-add-to-compare-" + key,
        className: "comfymodal-secondary-btn cm-compare-menu-item",
      });
      if (addB) pane.appendChild(el("div", { class: "comfymodal-studio-history-v2-action-row" }, [addB]));
    }

    pane.appendChild(el("div", { class: "comfymodal-studio-history-v2-action-row" }, [favBtn, favNote, retryBtn, genBtn, cellCompareBtn, note]));
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
    // Shared bounded status line for per-cell Browser Downloads (success and
    // truthful failure text).  Browser download never mutates export state.
    body.appendChild(el("div", {
      class: "comfymodal-studio-history-v2-action-note",
      "data-testid": CELL_DOWNLOAD_NOTE_TESTID,
      role: "status",
      "aria-live": "polite",
    }));
    // Separate bounded status line for per-cell configured-folder Export
    // (F10) — never conflated with the Browser Download note.
    body.appendChild(el("div", {
      class: "comfymodal-studio-history-v2-action-note",
      "data-testid": CELL_EXPORT_NOTE_TESTID,
      role: "status",
      "aria-live": "polite",
    }));
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

  // In-place refresh used by the Generate Original poll loop: rebuilds the
  // page from a fresh durable record (never an empty/loading screen) and
  // restores the selected cell when it still exists.
  function _rerenderPage(rec) {
    currentRecord = rec;
    closeAnyMenu();
    while (page.firstChild) page.removeChild(page.firstChild);
    page.appendChild(buildHeader(rec));
    page.appendChild(buildBody(rec));
    if (selectedCellKey) selectCell(selectedCellKey);
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
