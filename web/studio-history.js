// Modal Studio — History
//
// Gallery page backed by existing run/experiment data.
// Uses existing /comfymodal/run-history endpoint.
// Shows an image grid/gallery with clickable cards and a preview overlay/lightbox.
// Non-image runs get a fallback tile. Experiment grouping is preserved.
// Safe DOM rendering — no innerHTML for dynamic run data.
//
// Features:
// - Pagination (beyond first 50 records)
// - Filters: search, type, status, favorite only, preset, feature, date range, has image
// - Sorting: newest, oldest, fastest, slowest, preset A-Z, preset Z-A
// - Experiment grouping as toggle
// - Favorite star on cards and detail preview
// - Note editor in detail preview
//
// Image URL resolution order (delegated to studio-run-normalizer.js):
//   1. extra.primary_asset_id  → /assets/<id>
//   2. run.asset_id            → /assets/<id>
//   3. run.output_path         → /studio/outputs/<path>

import { resolveRunImageUrl, hasRunImage, normalizeStudioRun, normalizeGenerationSettings } from "./studio-run-normalizer.js";
import { listUnifiedHistory, updateRunAnnotation, saveRunOutput } from "./studio-backend-api.js";
import { loadExperimentIntoPlayground } from "./studio-playground.js";
import { el, createImagePreviewOverlay, registerLayerHandler } from "./studio-ui.js";

// ── Helpers ───────────────────────────────────────────────────────────────

function getRunExtra(run) {
  return (run && run.extra) || {};
}

/**
 * True when the record's output is already saved.  Reads the backend's
 * per-record saved state (defensively; absent state means not saved).
 */
function _isRecordOutputSaved(nr) {
  const raw = nr && nr.raw;
  if (!raw) return false;
  if (raw.output_saved === true) return true;
  if (raw.extra && raw.extra.output_saved === true) return true;
  return false;
}

function getRunStatus(run) {
  return run.status || run.state || "unknown";
}

function isCompleted(run) {
  const s = getRunStatus(run);
  return s === "completed" || s === "success" || s === "done";
}

function isFailed(run) {
  const s = getRunStatus(run);
  return s === "failed" || s === "error";
}

function _formatDuration(ms) {
  if (ms == null) return "?";
  if (ms < 1000) return ms.toFixed(0) + "ms";
  if (ms < 60000) return (ms / 1000).toFixed(1) + "s";
  var m = Math.floor(ms / 60000);
  var s = (ms % 60000) / 1000;
  return m + "m " + s.toFixed(0) + "s";
}

/**
 * Safely resolve the total count from API response data, falling back
 * to the length of the runs array when data.total is null/undefined.
 * Uses nullish coalescing to preserve an explicit zero from the backend.
 *
 * @param {object} data  - API response (may have .total, .runs, .run_history).
 * @param {Array}  runs  - Normalised runs array (already extracted from data).
 * @returns {number}
 */
export function resolveTotalCount(data, runs) {
  if (data && data.total != null) return data.total;
  if (Array.isArray(runs)) return runs.length;
  return 0;
}

/**
 * Build display-ready page-metadata from pagination parameters.
 * Returns an object with label, currentPage, totalPages, and total.
 *
 * Safe defaults:
 *   - total=0 produces label "(0 total)" and totalPages=1 (not NaN).
 *   - offset=0 produces currentPage=1.
 *
 * @param {number} offset
 * @param {number} limit
 * @param {number} total
 * @returns {{label: string, currentPage: number, totalPages: number, total: number}}
 */
export function formatPageMetadata(offset, limit, total) {
  var currentPage = Math.floor(offset / limit) + 1;
  var totalPages = Math.ceil(total / limit) || 1;
  return {
    label: "Page " + currentPage + "/" + totalPages + " (" + total + " total)",
    currentPage: currentPage,
    totalPages: totalPages,
    total: total,
  };
}

// ── Favorite Star ─────────────────────────────────────────────────────────

function renderFavoriteStar(nr, apiBase) {
  var isFav = nr.favorite;
  var star = el("button", {
    type: "button",
    class: "comfymodal-studio-favorite-star",
    "data-testid": "favorite-star",
    "aria-label": isFav ? "Remove from favorites" : "Add to favorites",
    "aria-pressed": isFav ? "true" : "false",
    text: isFav ? "\u2605" : "\u2606",
    style: "font-size:16px;color:" + (isFav ? "#fbbf24" : "#555") + ";",
    title: isFav ? "Remove from favorites" : "Add to favorites",
  });

  star.addEventListener("click", function (e) {
    e.stopPropagation();
    e.preventDefault();
    var wasFav = isFav;
    var newFav = !wasFav;
    isFav = newFav;
    nr.favorite = newFav;
    var runId = nr.id || nr.experimentId;
    star.textContent = newFav ? "\u2605" : "\u2606";
    star.style.color = newFav ? "#fbbf24" : "#555";
    star.setAttribute("aria-label", newFav ? "Remove from favorites" : "Add to favorites");
    star.setAttribute("aria-pressed", newFav ? "true" : "false");
    star.title = newFav ? "Remove from favorites" : "Add to favorites";

    updateRunAnnotation(apiBase, runId, { favorite: newFav }).then(function (result) {
      if (!result || result.status !== "ok") {
        isFav = wasFav;
        nr.favorite = wasFav;
        star.textContent = wasFav ? "\u2605" : "\u2606";
        star.style.color = wasFav ? "#fbbf24" : "#555";
        star.setAttribute("aria-label", wasFav ? "Remove from favorites" : "Add to favorites");
        star.setAttribute("aria-pressed", wasFav ? "true" : "false");
        star.title = wasFav ? "Remove from favorites" : "Add to favorites";
      }
    });
  });

  return star;
}

// ── Note Editor ───────────────────────────────────────────────────────────

function renderNoteEditor(nr, apiBase) {
  var container = el("div", {
    class: "comfymodal-studio-note-editor",
    "data-testid": "note-editor",
    style: "margin-top:8px;",
  });

  var currentNote = nr.note || "";
  var textarea = el("textarea", {
    class: "comfymodal-input comfymodal-studio-textarea",
    "data-testid": "note-textarea",
    style: "min-height:40px;font-size:11px;resize:vertical;box-sizing:border-box;",
    text: currentNote,
  });
  textarea.value = currentNote;

  var header = el("div", {
    style: "font-size:10px;color:#888;margin-bottom:2px;font-weight:600;text-transform:uppercase;",
    text: "Note",
  });

  var buttonRow = el("div", {
    style: "display:flex;gap:4px;margin-top:4px;align-items:center;",
  });

  var saveBtn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "note-save-btn",
    text: "Save",
    style: "font-size:10px;",
  });

  var cancelBtn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "note-cancel-btn",
    text: "Cancel",
    style: "font-size:10px;",
  });

  var statusEl = el("span", {
    "data-testid": "note-status",
    style: "font-size:9px;color:#888;margin-left:4px;",
  });

  buttonRow.appendChild(saveBtn);
  buttonRow.appendChild(cancelBtn);
  buttonRow.appendChild(statusEl);
  container.appendChild(header);
  container.appendChild(textarea);
  container.appendChild(buttonRow);

  var runId = nr.id || nr.experimentId;
  var isDirty = false;
  var savedNote = currentNote;

  textarea.addEventListener("input", function () {
    isDirty = textarea.value !== savedNote;
    if (isDirty) {
      statusEl.textContent = "Unsaved changes";
      statusEl.style.color = "#fbbf24";
    } else {
      statusEl.textContent = "";
    }
  });

  saveBtn.addEventListener("click", function () {
    if (!isDirty) return;
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    statusEl.textContent = "Saving...";
    statusEl.style.color = "#888";

    updateRunAnnotation(apiBase, runId, { note: textarea.value }).then(function (result) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save";
      if (result && result.status === "ok") {
        savedNote = textarea.value;
        nr.note = textarea.value;
        // Use backend updated_at as primary source, fall back to client time
        var backendUpdatedAt = result.annotations && result.annotations.updated_at;
        nr.noteUpdatedAt = backendUpdatedAt || new Date().toISOString();
        isDirty = false;
        statusEl.textContent = "Saved " + nr.noteUpdatedAt.substring(0, 19);
        statusEl.style.color = "#4ade80";
      } else {
        statusEl.textContent = "Save failed";
        statusEl.style.color = "#f87171";
      }
    });
  });

  cancelBtn.addEventListener("click", function () {
    textarea.value = savedNote;
    isDirty = false;
    statusEl.textContent = "";
  });

  return container;
}

// ── Timing Card ───────────────────────────────────────────────────────────
//
// Compact timing summary card for the preview overlay.
// Includes expandable advanced diagnostics.

function renderTimingCard(nr) {
  if (!nr.timingStages || nr.timingStages.length === 0) {
    // Fallback: timing summary string (progress annotation contract)
    if (nr.timingSummary && typeof nr.timingSummary === "string" && nr.timingSummary.length > 0) {
      return el("div", {
        class: "comfymodal-studio-timing-card",
        "data-testid": "timing-card",
        style: "margin-top:6px;padding:4px 8px;",
      }, [
        el("span", {
          class: "comfymodal-studio-timing-e2e",
          text: nr.timingSummary,
        }),
      ]);
    }
    if (nr.durationMs != null && nr.durationMs > 0) {
      return el("div", {
        class: "comfymodal-studio-timing-card",
        "data-testid": "timing-card",
        style: "margin-top:6px;padding:4px 8px;",
      }, [
        el("span", {
          class: "comfymodal-studio-timing-e2e",
          text: "Duration: " + _formatDuration(nr.durationMs),
        }),
      ]);
    }
    return null;
  }

  var card = el("div", {
    class: "comfymodal-studio-timing-card",
    "data-testid": "timing-card",
    style: "margin-top:6px;padding:4px 8px;",
  });

  // Primary E2E time
  var e2e = nr.timingStages.find(function (s) { return s.label === "End-to-End Total"; });
  if (e2e) {
    card.appendChild(el("span", {
      class: "comfymodal-studio-timing-e2e",
      text: "End-to-End Total: " + _formatDuration(e2e.durationMs),
    }));
  }

  // Top non-total stages (max 3)
  var nonTotalStages = nr.timingStages.filter(function (s) {
    return s.label !== "End-to-End Total" && s.durationMs > 0;
  }).sort(function (a, b) { return b.durationMs - a.durationMs; }).slice(0, 3);

  if (nonTotalStages.length > 0) {
    var tagRow = el("div", { class: "comfymodal-studio-timing-tags" });
    nonTotalStages.forEach(function (st) {
      tagRow.appendChild(el("span", {
        class: "comfymodal-studio-timing-tag",
        text: st.label + ": " + _formatDuration(st.durationMs),
      }));
    });
    card.appendChild(tagRow);
  }

  // Quality indicator
  if (nr._timingQuality && nr._timingQuality !== "complete") {
    card.appendChild(el("span", {
      class: "comfymodal-studio-timing-quality",
      text: nr._timingQuality + " quality",
    }));
  }

  // ── Advanced Diagnostics Toggle ─────────────────────────────────────
  if (nr.advancedTiming) {
    var advBtn = el("button", {
      class: "comfymodal-studio-advanced-timing-toggle",
      text: "\u25b6 Diagnostics",
      style: "font-size:9px;color:#666;cursor:pointer;background:none;border:none;padding:2px 0;margin-top:2px;display:block;",
      onclick: function () {
        var panel = card.querySelector(".comfymodal-studio-advanced-timing-panel");
        if (panel) {
          var isHidden = panel.style.display === "none" || panel.style.display === "";
          panel.style.display = isHidden ? "block" : "none";
          advBtn.textContent = isHidden ? "\u25bc Diagnostics" : "\u25b6 Diagnostics";
        }
      },
    });
    card.appendChild(advBtn);

    var advPanel = el("div", {
      class: "comfymodal-studio-advanced-timing-panel",
      style: "display:none;font-size:9px;color:#666;margin-top:2px;padding:2px 4px;background:#0a0a0a;border:1px solid #1a1a1a;border-radius:2px;",
    });

    var diag = nr.advancedTiming;
    var diagLines = [];

    if (diag.traceVersion) {
      // Display exact trace version without adding another "v" prefix
      diagLines.push("Trace Version: " + diag.traceVersion);
    }
    diagLines.push("Quality: " + diag.timingQuality + " \u2014 " + (diag.timingReason || ""));
    if (diag.missingFields && diag.missingFields.length > 0) {
      diagLines.push("Missing: " + diag.missingFields.join(", "));
    }
    if (diag.rawDeltasMs && Object.keys(diag.rawDeltasMs).length > 0) {
      diagLines.push("Raw deltas_ms: " + JSON.stringify(diag.rawDeltasMs).substring(0, 120) + "\u2026");
    }
    if (diag.rawDerivedMs && Object.keys(diag.rawDerivedMs).length > 0) {
      diagLines.push("Raw derived_ms: " + JSON.stringify(diag.rawDerivedMs).substring(0, 120) + "\u2026");
    }
    if (diag.rawStages && Object.keys(diag.rawStages).length > 0) {
      diagLines.push("Raw stages: " + JSON.stringify(diag.rawStages).substring(0, 120) + "\u2026");
    }
    if (diag.wallClockTrace) {
      diagLines.push("Wall-Clock Trace: " + JSON.stringify(diag.wallClockTrace).substring(0, 120) + "\u2026");
    }
    if (diag.schedulerTrace) {
      diagLines.push("Scheduler Trace: " + JSON.stringify(diag.schedulerTrace).substring(0, 120) + "\u2026");
    }
    if (diag.sources && Object.keys(diag.sources).length > 0) {
      diagLines.push("Sources: " + JSON.stringify(diag.sources).substring(0, 120) + "\u2026");
    }
    if (diag.backendTimingSources && Object.keys(diag.backendTimingSources).length > 0) {
      diagLines.push("Backend Sources: " + JSON.stringify(diag.backendTimingSources).substring(0, 120) + "\u2026");
    }

    diagLines.forEach(function (line) {
      advPanel.appendChild(el("div", { text: line, style: "margin:1px 0;" }));
    });

    // Full stage list
    if (nr.timingStages && nr.timingStages.length > 0) {
      advPanel.appendChild(el("div", {
        text: "All Stages:",
        style: "margin:3px 0 1px;font-weight:600;color:#888;",
      }));
      nr.timingStages.forEach(function (st) {
        advPanel.appendChild(el("div", {
          text: "  " + st.label + ": " + _formatDuration(st.durationMs) + " (" + st.source + ")",
          style: "margin:0;padding-left:6px;",
        }));
      });
    }

    card.appendChild(advPanel);
  }

  return card;
}

// ── Main renderer ─────────────────────────────────────────────────────────

export function renderHistory(state, context) {
  const container = el("div", { class: "comfymodal-studio-history" });
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // ── Safe child removal (tolerates synchronous re-entrancy) ────────
  // Takes a snapshot of childNodes before iterating so that blur/change
  // events fired during removal cannot corrupt the live collection.
  // Each node is removed only if it is still a child of the container.
  function _removeAllChildren(el) {
    var nodes = Array.from(el.childNodes);
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (node.parentNode === el) {
        try { node.remove(); } catch { /* detached during re-entry */ }
      }
    }
  }

  // ── Internal state ──────────────────────────────────────────────────
  var queryParams = {
    page: 1,
    page_size: 50,
    search: "",
    type: "",
    status: "",
    favorite: false,
    preset: "",
    feature: "",
    date_from: "",
    date_to: "",
    has_image: false,
    sort: "newest",
  };
  var previewRun = null;
  var previewController = null;
  var groupExperiments = false;
  var totalCount = 0;
  var _COLUMNS_KEY = "comfymodal-studio-history-columns";
  var columnCount = parseInt(localStorage.getItem(_COLUMNS_KEY), 10) || 6;
  if (columnCount < 2 || columnCount > 12) columnCount = 6;

  // ── Request dedup + cancellation ────────────────────────────────────
  var _abortController = null;
  var _lastRequestEpoch = 0;
  /** Cache key for identical page queries (page, page_size, search, type, status, sort, favorite) */
  var _queryCache = {};
  var _QUERY_CACHE_TTL = 2000; // 2s
  var _QUERY_CACHE_MAX = 50;   // max entries before pruning

  // ── Debounce helper ─────────────────────────────────────────────────
  var _searchTimer = null;

  // ── Filter/Sort/Pagination Bar ─────────────────────────────────────
  function renderFilterBar() {
    var bar = el("div", {
      class: "comfymodal-studio-filter-bar",
      style: "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px;",
    });

    // Search input (debounced to avoid fetch on every keystroke)
    var searchInput = el("input", {
      type: "text",
      class: "comfymodal-input comfymodal-studio-text-input",
      placeholder: "Search...",
      value: queryParams.search,
      style: "width:140px;font-size:11px;padding:4px 6px;",
      "data-testid": "history-search",
    });
    searchInput.addEventListener("input", function () {
      queryParams.search = searchInput.value;
      queryParams.offset = 0;
      clearTimeout(_searchTimer);
      _searchTimer = setTimeout(fetchAndRender, 300);
    });

    // Type filter
    var typeSelect = el("select", {
      class: "comfymodal-input comfymodal-studio-select",
      "data-testid": "history-type-filter",
      style: "font-size:11px;padding:3px 4px;width:90px;",
    });
    var typeOpts = ["", "run", "experiment", "experiment_cell", "studio_run"];
    typeOpts.forEach(function (t) {
      var opt = el("option", { value: t, text: t || "All Types" });
      if (t === queryParams.type) opt.selected = true;
      typeSelect.appendChild(opt);
    });
    typeSelect.addEventListener("change", function () {
      queryParams.type = typeSelect.value;
      queryParams.offset = 0;
      fetchAndRender();
    });

    // Status filter
    var statusSelect = el("select", {
      class: "comfymodal-input comfymodal-studio-select",
      "data-testid": "history-status-filter",
      style: "font-size:11px;padding:3px 4px;width:100px;",
    });
    var statusOpts = ["", "completed", "failed", "error", "in_progress", "queued"];
    statusOpts.forEach(function (s) {
      var opt = el("option", { value: s, text: s || "All Status" });
      if (s === queryParams.status) opt.selected = true;
      statusSelect.appendChild(opt);
    });
    statusSelect.addEventListener("change", function () {
      queryParams.status = statusSelect.value;
      queryParams.offset = 0;
      fetchAndRender();
    });

    // Sort select
    var sortSelect = el("select", {
      class: "comfymodal-input comfymodal-studio-select",
      "data-testid": "history-sort",
      style: "font-size:11px;padding:3px 4px;width:110px;",
    });
    var sortOpts = [
      { value: "newest", label: "Newest" },
      { value: "oldest", label: "Oldest" },
      { value: "fastest", label: "Fastest" },
      { value: "slowest", label: "Slowest" },
      { value: "preset_az", label: "Preset A-Z" },
      { value: "preset_za", label: "Preset Z-A" },
    ];
    sortOpts.forEach(function (s) {
      var opt = el("option", { value: s.value, text: s.label });
      if (s.value === queryParams.sort) opt.selected = true;
      sortSelect.appendChild(opt);
    });
    sortSelect.addEventListener("change", function () {
      queryParams.sort = sortSelect.value;
      queryParams.offset = 0;
      fetchAndRender();
    });

    // Favorite only checkbox
    var favLabel = el("label", {
      style: "display:flex;align-items:center;gap:3px;font-size:10px;color:#aaa;cursor:pointer;",
    });
    var favCb = el("input", {
      type: "checkbox",
      checked: queryParams.favorite,
      "data-testid": "history-fav-only",
    });
    favCb.addEventListener("change", function () {
      queryParams.favorite = favCb.checked;
      queryParams.offset = 0;
      fetchAndRender();
    });
    favLabel.appendChild(favCb);
    favLabel.appendChild(document.createTextNode("Favorites only"));

    // Has image checkbox
    var imgLabel = el("label", {
      style: "display:flex;align-items:center;gap:3px;font-size:10px;color:#aaa;cursor:pointer;",
    });
    var imgCb = el("input", {
      type: "checkbox",
      checked: queryParams.has_image,
      "data-testid": "history-has-image",
    });
    imgCb.addEventListener("change", function () {
      queryParams.has_image = imgCb.checked;
      queryParams.offset = 0;
      fetchAndRender();
    });
    imgLabel.appendChild(imgCb);
    imgLabel.appendChild(document.createTextNode("Has image"));

    // Preset filter input
    var presetInput = el("input", {
      type: "text",
      class: "comfymodal-input comfymodal-studio-text-input",
      placeholder: "Preset ID...",
      value: queryParams.preset,
      style: "width:100px;font-size:11px;padding:3px 4px;",
      "data-testid": "history-preset-filter",
    });
    presetInput.addEventListener("input", function () {
      queryParams.preset = presetInput.value;
      queryParams.offset = 0;
      fetchAndRender();
    });

    // Feature filter input
    var featureInput = el("input", {
      type: "text",
      class: "comfymodal-input comfymodal-studio-text-input",
      placeholder: "Feature...",
      value: queryParams.feature,
      style: "width:80px;font-size:11px;padding:3px 4px;",
      "data-testid": "history-feature-filter",
    });
    featureInput.addEventListener("input", function () {
      queryParams.feature = featureInput.value;
      queryParams.offset = 0;
      fetchAndRender();
    });

    // Date range
    var dateFrom = el("input", {
      type: "date",
      class: "comfymodal-input",
      value: queryParams.date_from,
      style: "font-size:10px;padding:2px 4px;width:120px;",
      "data-testid": "history-date-from",
    });
    dateFrom.addEventListener("change", function () {
      queryParams.date_from = dateFrom.value;
      queryParams.offset = 0;
      fetchAndRender();
    });
    var dateTo = el("input", {
      type: "date",
      class: "comfymodal-input",
      value: queryParams.date_to,
      style: "font-size:10px;padding:2px 4px;width:120px;",
      "data-testid": "history-date-to",
    });
    dateTo.addEventListener("change", function () {
      queryParams.date_to = dateTo.value;
      queryParams.offset = 0;
      fetchAndRender();
    });

    // Group toggle
    var groupLabel = el("label", {
      style: "display:flex;align-items:center;gap:3px;font-size:10px;color:#aaa;cursor:pointer;",
    });
    var groupCb = el("input", {
      type: "checkbox",
      checked: groupExperiments,
      "data-testid": "history-group-toggle",
    });
    groupCb.addEventListener("change", function () {
      groupExperiments = groupCb.checked;
      fetchAndRender();
    });
    groupLabel.appendChild(groupCb);
    groupLabel.appendChild(document.createTextNode("Group experiments"));

    // Column count selector
    var colSelector = el("div", {
      class: "comfymodal-studio-history-column-select",
      "data-testid": "history-column-select",
    }, [
      el("label", { text: "Cols" }),
    ]);
    var colInput = el("input", {
      type: "number",
      min: "2",
      max: "12",
      value: String(columnCount),
      "data-testid": "history-columns-input",
      "aria-label": "Number of columns",
    });
    colInput.addEventListener("change", function () {
      var val = parseInt(colInput.value, 10);
      if (isNaN(val) || val < 2) val = 2;
      if (val > 12) val = 12;
      columnCount = val;
      colInput.value = String(columnCount);
      localStorage.setItem(_COLUMNS_KEY, String(columnCount));
      fetchAndRender();
    });
    colSelector.appendChild(colInput);

    // Pagination info + controls
    var pageInfo = el("span", {
      "data-testid": "history-page-info",
      style: "font-size:10px;color:#888;margin-left:auto;",
    });

    var prevBtn = el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "history-prev",
      text: "\u2190 Prev",
      style: "font-size:10px;padding:2px 8px;",
      disabled: queryParams.page <= 1,
      onclick: function () {
        if (queryParams.page > 1) {
          queryParams.page -= 1;
          fetchAndRender();
        }
      },
    });

    var nextBtn = el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "history-next",
      text: "Next \u2192",
      style: "font-size:10px;padding:2px 8px;",
      disabled: !_hasMore,
      onclick: function () {
        queryParams.page += 1;
        fetchAndRender();
      },
    });

    bar.appendChild(searchInput);
    bar.appendChild(typeSelect);
    bar.appendChild(statusSelect);
    bar.appendChild(sortSelect);
    bar.appendChild(favLabel);
    bar.appendChild(imgLabel);
    bar.appendChild(presetInput);
    bar.appendChild(featureInput);
    bar.appendChild(dateFrom);
    bar.appendChild(dateTo);
    bar.appendChild(groupLabel);
    bar.appendChild(colSelector);
    bar.appendChild(prevBtn);
    bar.appendChild(nextBtn);
    bar.appendChild(pageInfo);

    // Update page info via shared pure helper (using server total)
    var meta = formatPageMetadata((queryParams.page - 1) * queryParams.page_size, queryParams.page_size, totalCount);
    pageInfo.textContent = meta.label;

    return bar;
  }

  // ── Preview Overlay ──────────────────────────────────────────────────
  function renderPreviewOverlay() {
    const existing = container.querySelector(".comfymodal-studio-preview-overlay");
    if (previewController) {
      previewController.close(false);
      previewController = null;
    } else if (existing) {
      existing.remove();
    }
    if (!previewRun) return;

    const nr = previewRun;
    const imageUrl = nr.imageUrl;
    const rid = nr.id || "unknown";
    const status = nr.status;
    const promptText = (nr.prompt != null ? nr.prompt : rid).substring(0, 200);

    // Build metadata using normalized fields (shared normalizer for settings)
    const metaItems = [];
    if (nr.durationMs != null && nr.durationMs > 0) {
      metaItems.push({ label: "Duration", value: _formatDuration(nr.durationMs) });
    }
    if (nr.startedAt != null && nr.startedAt) {
      metaItems.push({ label: "Generated", value: nr.startedAt.substring(0, 19) });
    }
    if (nr.presetLabel != null && nr.presetLabel) {
      metaItems.push({ label: "Preset", value: nr.presetLabel.substring(0, 20) });
    } else if (nr.presetId != null && nr.presetId) {
      metaItems.push({ label: "Preset", value: nr.presetId.substring(0, 20) });
    }
    if (nr.featureId) {
      metaItems.push({ label: "Feature", value: nr.featureId });
    }
    const rc = nr.resolvedControls || {};
    const rqc = nr.requestedControls || {};
    var normalizedSettings = normalizeGenerationSettings(rc, rqc);
    if (normalizedSettings.seed != null) metaItems.push({ label: "Seed", value: String(normalizedSettings.seed) });
    if (normalizedSettings.steps != null) metaItems.push({ label: "Steps", value: String(normalizedSettings.steps) });
    if (normalizedSettings.cfg != null) metaItems.push({ label: "CFG", value: String(normalizedSettings.cfg) });
    if (normalizedSettings.guidance != null && normalizedSettings.cfg == null) {
      metaItems.push({ label: "Guidance", value: String(normalizedSettings.guidance) });
    }
    if (normalizedSettings.sampler != null) metaItems.push({ label: "Sampler", value: String(normalizedSettings.sampler) });
    if (normalizedSettings.scheduler != null) metaItems.push({ label: "Scheduler", value: String(normalizedSettings.scheduler) });
    if (normalizedSettings.denoise != null) metaItems.push({ label: "Denoise", value: String(normalizedSettings.denoise) });
    if (normalizedSettings.width != null && normalizedSettings.height != null) {
      metaItems.push({ label: "Size", value: normalizedSettings.width + "\u00d7" + normalizedSettings.height });
    }
    if (nr.workflowHash) metaItems.push({ label: "Workflow", value: nr.workflowHash.substring(0, 8) + "\u2026" });
    if (nr.snapshotId) metaItems.push({ label: "Snapshot", value: nr.snapshotId.substring(0, 12) + "\u2026" });

    // Track trigger card for focus return
    var triggerCard = container.querySelector(".comfymodal-studio-history-card[data-preview-trigger]");

    function closePreview() {
      previewRun = null;
      // Cleanup (layer handler, zoom, DOM removal) is handled by the
      // overlay's internal close() which calls this callback after cleanup.
      if (triggerCard && typeof triggerCard.focus === "function") {
        triggerCard.focus();
      }
    }

    var sections = [];

    // Info bar: favorite star, status, prompt
    sections.push(el("div", { class: "comfymodal-studio-preview-info" }, [
      renderFavoriteStar(nr, apiBase),
      el("span", { class: "comfymodal-studio-preview-status", text: status }),
      el("span", { class: "comfymodal-studio-preview-prompt", text: promptText }),
    ]));

    // Generation settings metadata
    if (metaItems.length > 0) {
      sections.push(el("div", { class: "comfymodal-studio-preview-meta" },
        metaItems.map(function (item) {
          return el("span", {
            class: "comfymodal-studio-preview-meta-item",
            text: item.label + ": " + item.value,
          });
        })
      ));
    }

    // Timing card
    var timingCard = renderTimingCard(nr);
    if (timingCard) sections.push(timingCard);

    // Note editor
    sections.push(renderNoteEditor(nr, apiBase));

    // Save-output action (single-output backend save).  Button visibility
    // follows the record saved state; the request targets only the
    // selected (primary) output.
    var saveConfig = null;
    if (imageUrl && nr.id && !_isRecordOutputSaved(nr)) {
      saveConfig = {
        saved: false,
        onSave: async function () {
          const res = await saveRunOutput(apiBase, rid, { output_index: 0 });
          if (!res || res.status !== "ok") {
            throw new Error((res && res.message) || "Save request failed");
          }
          if (nr.raw) nr.raw.output_saved = true;
          if (nr.raw && nr.raw.extra) nr.raw.extra.output_saved = true;
          nr.outputSaved = true;
          renderPreviewOverlay();
          return true;
        },
      };
    }

    var preview = createImagePreviewOverlay({
      imageUrl: imageUrl,
      alt: promptText,
      onClose: closePreview,
      sections: sections,
      focusTrap: true,
      saveOutput: saveConfig,
    });
    previewController = preview;

    container.appendChild(preview.overlay);

    // Move focus to close button
    var closeBtn = preview.overlay.querySelector(".comfymodal-studio-preview-overlay-close");
    if (closeBtn && typeof closeBtn.focus === "function") {
      requestAnimationFrame(function () { closeBtn.focus(); });
    }
  }

  function openPreview(run) {
    previewRun = run;
    // Mark the triggering card for focus return on close
    var cards = container.querySelectorAll(".comfymodal-studio-history-card");
    cards.forEach(function (c) { c.removeAttribute("data-preview-trigger"); });
    var activeCard = container.querySelector(".comfymodal-studio-history-card:focus-within, .comfymodal-studio-history-card:hover");
    if (activeCard) activeCard.setAttribute("data-preview-trigger", "");
    renderPreviewOverlay();
  }

  // ── Fetch and render ─────────────────────────────────────────────────
  var _hasMore = false;

  function buildCacheKey() {
    return JSON.stringify({
      page: queryParams.page,
      page_size: queryParams.page_size,
      search: queryParams.search,
      type: queryParams.type,
      status: queryParams.status,
      favorite: queryParams.favorite,
      preset: queryParams.preset,
      feature: queryParams.feature,
      date_from: queryParams.date_from,
      date_to: queryParams.date_to,
      has_image: queryParams.has_image,
      sort: queryParams.sort,
    });
  }

  function fetchAndRender() {
    // Abort any in-flight request
    if (_abortController) {
      _abortController.abort();
    }
    _abortController = new AbortController();
    var signal = _abortController.signal;
    var thisEpoch = ++_lastRequestEpoch;

    // Clear previous performance marks/measures to avoid accumulation
    if (typeof performance !== "undefined" && performance.clearMarks) {
      performance.clearMarks("history-request-start");
      performance.clearMarks("history-response-received");
      performance.clearMarks("history-normalize-start");
      performance.clearMarks("history-dom-start");
      performance.clearMarks("history-first-card");
      performance.clearMarks("history-image-decode-start");
      performance.clearMarks("history-image-decode-end");
    }
    if (typeof performance !== "undefined" && performance.clearMeasures) {
      performance.clearMeasures("history-cached");
      performance.clearMeasures("history-request");
      performance.clearMeasures("history-normalize");
      performance.clearMeasures("history-dom-creation");
      performance.clearMeasures("history-first-card-render");
      performance.clearMeasures("history-image-decode");
    }

    // Performance mark: request start
    if (typeof performance !== "undefined" && performance.mark) {
      performance.mark("history-request-start");
    }

    // Check cache for identical recent query
    var cacheKey = buildCacheKey();
    var cached = _queryCache[cacheKey];
    if (cached && (Date.now() - cached.ts) < _QUERY_CACHE_TTL) {
      if (typeof performance !== "undefined" && performance.measure) {
        try { performance.measure("history-cached", "history-request-start"); } catch (e) {}
      }
      renderItems(cached.data);
      _abortController = null;
      return;
    }

    // Clear (safe helper tolerates re-entrant blur/change during removal)
    _removeAllChildren(container);

    // Add filter bar
    container.appendChild(renderFilterBar());

    // Loading state
    container.appendChild(el("div", {
      class: "comfymodal-studio-card",
      text: "Loading history...",
    }));

    // Build query params for API — use page/page_size
    var apiParams = {
      page: queryParams.page,
      page_size: queryParams.page_size,
    };
    if (queryParams.search) apiParams.search = queryParams.search;
    if (queryParams.type) apiParams.type = queryParams.type;
    if (queryParams.status) apiParams.status = queryParams.status;
    if (queryParams.favorite) apiParams.favorite = true;
    if (queryParams.preset) apiParams.preset = queryParams.preset;
    if (queryParams.feature) apiParams.feature = queryParams.feature;
    if (queryParams.date_from) apiParams.date_from = queryParams.date_from;
    if (queryParams.date_to) apiParams.date_to = queryParams.date_to;
    if (queryParams.has_image) apiParams.has_image = true;
    if (queryParams.sort) apiParams.sort = queryParams.sort;

    listUnifiedHistory(apiBase, apiParams, signal).then(function (result) {
      // Ignore out-of-order responses
      if (thisEpoch !== _lastRequestEpoch) return;
      if (!result || signal.aborted) {
        if (!signal.aborted) {
          _removeAllChildren(container);
          container.appendChild(renderFilterBar());
          container.appendChild(el("div", {
            class: "comfymodal-studio-card",
            style: "color:var(--color-danger)",
            text: "Failed to load history.",
          }));
        }
        return;
      }

      // Performance mark: response received
      if (typeof performance !== "undefined" && performance.mark) {
        performance.mark("history-response-received");
      }

      // Cache the result with bounded size
      _queryCache[cacheKey] = { data: result, ts: Date.now() };
      var now = Date.now();
      var keys = Object.keys(_queryCache);
      // Prune stale entries
      keys.forEach(function (k) {
        if (now - _queryCache[k].ts > _QUERY_CACHE_TTL * 2) {
          delete _queryCache[k];
        }
      });
      // Enforce max cache size (evict oldest if over limit)
      if (keys.length > _QUERY_CACHE_MAX) {
        var sorted = keys.slice().sort(function (a, b) {
          return _queryCache[a].ts - _queryCache[b].ts;
        });
        while (Object.keys(_queryCache).length > _QUERY_CACHE_MAX) {
          delete _queryCache[sorted.shift()];
        }
      }

      totalCount = result.total || 0;
      _hasMore = result.has_more || false;

      renderItems(result);
    }).catch(function (err) {
      if (err && err.name === "AbortError") return;
      if (thisEpoch !== _lastRequestEpoch) return;
      _removeAllChildren(container);
      container.appendChild(renderFilterBar());
      var errorCard = el("div", { class: "comfymodal-studio-card" });
      errorCard.appendChild(el("p", {
        style: "color:var(--color-danger)",
        text: "Failed to load history: " + (err && err.message ? err.message : "unknown error"),
      }));
      errorCard.appendChild(el("button", {
        class: "comfymodal-secondary-btn",
        text: "Retry",
        style: "margin-top:8px",
        onclick: fetchAndRender,
      }));
      container.appendChild(errorCard);
    });
  }

  // ── Render items helper (called by fetchAndRender) ──────────────────────
  function renderItems(result) {
    // Performance mark: normalization start
    if (typeof performance !== "undefined" && performance.mark) {
      performance.mark("history-normalize-start");
    }

    _removeAllChildren(container);
    container.appendChild(renderFilterBar());

    var items = result.items || [];
    if (items.length === 0) {
      container.appendChild(el("div", {
        class: "comfymodal-studio-card",
        text: "No run history yet. Runs will appear here once you create experiments.",
      }));
      return;
    }

    // Normalize all items for consistent field access
    var normalizedItems = items.map(function (item) {
      return normalizeStudioRun(item, apiBase);
    }).filter(Boolean);

    // Performance mark: DOM creation start
    if (typeof performance !== "undefined" && performance.mark) {
      performance.mark("history-dom-start");
    }

    // Use DocumentFragment for batch DOM insertion
    var fragment = document.createDocumentFragment();
    var gallery = el("div", {
      class: "comfymodal-studio-history-gallery",
      style: "--columns:" + columnCount + ";",
      "data-testid": "history-gallery",
    });
    fragment.appendChild(gallery);

    // Render cards into gallery (with optional experiment grouping)
    if (groupExperiments) {
      // Group by stable experiment_id (empty/none stays individual)
      var groups = {};
      normalizedItems.forEach(function (nr) {
        var eid = nr.experimentId || "";
        if (!groups[eid]) groups[eid] = [];
        groups[eid].push(nr);
      });
      var groupIds = Object.keys(groups).sort();
      var cardIndex = 0;
      groupIds.forEach(function (eid) {
        var members = groups[eid];
        if (eid && members.length > 1) {
          // Multi-run experiment: render as grouped tile
          var groupCard = renderGroup(eid, members, apiBase, openPreview, columnCount);
          gallery.appendChild(groupCard);
          if (cardIndex === 0 && typeof performance !== "undefined" && performance.mark) {
            performance.mark("history-first-card");
          }
          cardIndex += members.length;
        } else {
          // Single run or no experiment: render individual card
          members.forEach(function (nr) {
            var card = renderHistoryCard(nr, apiBase, openPreview);
            gallery.appendChild(card);
            if (cardIndex === 0 && typeof performance !== "undefined" && performance.mark) {
              performance.mark("history-first-card");
            }
            cardIndex++;
          });
        }
      });
    } else {
      // Default: all individual cards (ungrouped)
      normalizedItems.forEach(function (nr, index) {
        var card = renderHistoryCard(nr, apiBase, openPreview);
        gallery.appendChild(card);

        // Performance mark: first card rendered
        if (index === 0 && typeof performance !== "undefined" && performance.mark) {
          performance.mark("history-first-card");
        }
      });
    }

    // Performance mark: image decode start (lazy, async)
    if (typeof performance !== "undefined" && performance.mark) {
      performance.mark("history-image-decode-start");
    }

    // Async image decode for thumbnails via requestIdleCallback or setTimeout
    var decodeFn = function () {
      var imgs = gallery.querySelectorAll("img");
      var imgArray = Array.from(imgs);
      var decodeNext = function (idx) {
        if (idx >= imgArray.length) {
          if (typeof performance !== "undefined" && performance.mark) {
            performance.mark("history-image-decode-end");
          }
          if (typeof performance !== "undefined" && performance.measure) {
            try { performance.measure("history-image-decode", "history-image-decode-start", "history-image-decode-end"); } catch (e) {}
          }
          return;
        }
        var img = imgArray[idx];
        if (img && typeof img.decode === "function") {
          img.decode().then(function () {
            setTimeout(function () { decodeNext(idx + 1); }, 0);
          }).catch(function () {
            setTimeout(function () { decodeNext(idx + 1); }, 0);
          });
        } else {
          setTimeout(function () { decodeNext(idx + 1); }, 0);
        }
      };
      decodeNext(0);
    };
    if (typeof requestIdleCallback === "function") {
      requestIdleCallback(decodeFn, { timeout: 1000 });
    } else {
      setTimeout(decodeFn, 50);
    }

    // Update page info
    var pageInfoEl = container.querySelector('[data-testid="history-page-info"]');
    if (pageInfoEl) {
      var meta = formatPageMetadata((queryParams.page - 1) * queryParams.page_size, queryParams.page_size, totalCount);
      pageInfoEl.textContent = meta.label;
    }

    container.appendChild(fragment);

    // Performance measures
    if (typeof performance !== "undefined" && performance.measure) {
      try {
        performance.measure("history-request", "history-request-start", "history-response-received");
        performance.measure("history-normalize", "history-response-received", "history-normalize-start");
        performance.measure("history-dom-creation", "history-dom-start");
        performance.measure("history-first-card-render", "history-request-start", "history-first-card");
      } catch (e) {}
    }
  }

  fetchAndRender();
  return container;
}

// ── History Card ──────────────────────────────────────────────────────────

function renderHistoryCard(nr, apiBase, openPreview) {
  var hasImage = !!nr.imageUrl;
  var imageUrl = nr.imageUrl || null;
  var status = nr.status;
  var promptText = (nr.prompt || nr.id || "unknown").substring(0, 60);
  var time = nr.startedAt || "";

  var isCardCompleted = nr.status === "completed" || nr.status === "success" || nr.status === "done";
  var isCardFailed = nr.status === "failed" || nr.status === "error";

  var card = el("div", {
    class: "comfymodal-studio-history-card"
      + (isCardCompleted ? " completed" : "")
      + (isCardFailed ? " failed" : ""),
    tabindex: "0",
    role: "button",
    "aria-label": "View details for " + promptText,
    onclick: function () { openPreview(nr); },
  });

  // Favorite star on card
  var starContainer = el("div", {
    style: "position:absolute;top:4px;right:4px;z-index:2;",
  });
  starContainer.appendChild(renderFavoriteStar(nr, apiBase));
  card.appendChild(starContainer);

  // Thumbnail or fallback
  if (imageUrl) {
    card.appendChild(el("img", {
      class: "comfymodal-studio-history-thumb",
      src: imageUrl,
      alt: promptText,
      loading: "lazy",
    }));
    // Time badge at bottom right (always visible)
    if (time) {
      var shortTime = time.length > 16 ? time.substring(11, 16) : time;
      card.appendChild(el("span", {
        class: "comfymodal-studio-history-card-time-badge",
        text: shortTime,
      }));
    }
  } else {
    var fallback = el("div", { class: "comfymodal-studio-history-fallback" });
    fallback.appendChild(el("span", {
      class: "comfymodal-studio-history-fallback-icon",
      text: "\u{1F5C4}",
    }));
    fallback.appendChild(el("span", {
      class: "comfymodal-studio-history-fallback-label",
      text: promptText.substring(0, 30),
    }));
    card.appendChild(fallback);
  }

  // Overlay with status/prompt on hover
  var overlayEl = el("div", { class: "comfymodal-studio-history-card-overlay" });
  overlayEl.appendChild(el("span", {
    class: "comfymodal-studio-history-card-status",
    text: status,
  }));
  overlayEl.appendChild(el("span", {
    class: "comfymodal-studio-history-card-prompt",
    text: promptText,
  }));
  if (time) {
    overlayEl.appendChild(el("span", {
      class: "comfymodal-studio-history-card-time",
      text: time,
    }));
  }
  card.appendChild(overlayEl);

  return card;
}

function renderHistoryGallery(runs, apiBase, openPreview, columnCount) {
  columnCount = typeof columnCount === "number" ? columnCount : 6;
  var gallery = el("div", {
    class: "comfymodal-studio-history-gallery",
    style: "--columns:" + columnCount + ";",
    "data-testid": "history-gallery",
  });

  runs.forEach(function (nr) {
    var card = renderHistoryCard(nr, apiBase, openPreview);
    gallery.appendChild(card);
  });

  return gallery;
}

// ── Experiment Tile ────────────────────────────────────────────────────────
//
// Compact experiment tile shown in the default (ungrouped) History view.
// Collapses all experiment_cell rows sharing an experimentId into one tile.
// Clicking opens the full experiment grid in the Playground via the shared
// loadExperimentIntoPlayground loader.  Errors surface as an inline message
// without leaving the current page.

function renderExperimentTile(expId, groupRuns, apiBase, context, state) {
  var firstRun = groupRuns[0] || {};
  var completedCount = groupRuns.filter(function (r) { return isCompleted(r); }).length;
  var failedCount = groupRuns.filter(function (r) { return isFailed(r); }).length;
  var totalCount = groupRuns.length;

  var hasRunning = groupRuns.some(function (r) {
    var s = getRunStatus(r);
    return s === "in_progress" || s === "running" || s === "queued";
  });

  var overallStatus;
  if (hasRunning) overallStatus = "running";
  else if (failedCount > 0 && completedCount === 0) overallStatus = "failed";
  else if (completedCount === totalCount && totalCount > 0) overallStatus = "completed";
  else if (completedCount > 0 && failedCount > 0) overallStatus = "partial";
  else if (completedCount > 0) overallStatus = "running";
  else overallStatus = "unknown";

  var statusClass = overallStatus === "completed" ? " completed"
    : overallStatus === "failed" ? " failed"
    : overallStatus === "running" ? " running" : "";

  var titleText = "Experiment";

  var card = el("div", {
    class: "comfymodal-studio-history-card comfymodal-studio-experiment-tile" + statusClass,
    tabindex: "0",
    role: "button",
    "data-expid": expId,
    "data-testid": "experiment-tile",
    "aria-label": "Open experiment " + expId + " in playground",
  });

  // Experiment badge / label
  var badgeRow = el("div", {
    style: "display:flex;align-items:center;gap:6px;padding:8px 8px 2px;width:100%;box-sizing:border-box;",
  });
  badgeRow.appendChild(el("span", {
    class: "comfymodal-studio-exp-tile-badge",
    text: "EXP",
    "aria-hidden": "true",
  }));
  badgeRow.appendChild(el("span", {
    class: "comfymodal-studio-exp-tile-title",
    text: titleText,
  }));
  card.appendChild(badgeRow);

  // Status line
  var statusLine = el("div", {
    style: "display:flex;align-items:center;gap:6px;padding:0 8px;font-size:10px;width:100%;box-sizing:border-box;",
  });
  var statusColor = overallStatus === "completed" ? "#4ade80"
    : overallStatus === "failed" ? "#f87171"
    : overallStatus === "running" ? "#fbbf24" : "#888";
  statusLine.appendChild(el("span", {
    style: "color:" + statusColor + ";font-weight:600;text-transform:uppercase;",
    text: overallStatus,
  }));
  statusLine.appendChild(el("span", {
    style: "color:#888;",
    text: "\u00b7 " + totalCount + " cell" + (totalCount !== 1 ? "s" : ""),
  }));
  if (completedCount > 0) {
    statusLine.appendChild(el("span", {
      style: "color:#4ade80;",
      text: "\u00b7 " + completedCount + " done",
    }));
  }
  if (failedCount > 0) {
    statusLine.appendChild(el("span", {
      style: "color:#f87171;",
      text: "\u00b7 " + failedCount + " failed",
    }));
  }
  card.appendChild(statusLine);

  // Image area: 2x2 grid for 4+ images, single image for <4
  if (groupRuns.length > 0) {
    var imgArea = el("div", { class: "comfymodal-studio-exp-tile-images" });

    if (totalCount >= 4) {
      // 2x2 grid of first 4 images
      var grid = el("div", { class: "comfymodal-studio-exp-tile-grid" });
      var limit = Math.min(groupRuns.length, 4);
      for (var ti = 0; ti < limit; ti++) {
        var cellRun = groupRuns[ti];
        if (cellRun.imageUrl) {
          grid.appendChild(el("img", {
            class: "comfymodal-studio-exp-tile-grid-img",
            src: cellRun.imageUrl,
            alt: "",
            loading: "lazy",
          }));
        } else {
          grid.appendChild(el("div", { class: "comfymodal-studio-exp-tile-grid-empty" }));
        }
      }
      imgArea.appendChild(grid);
    } else {
      // Single image for 1-3 total tiles
      var firstWithImg = null;
      for (var si = 0; si < groupRuns.length; si++) {
        if (groupRuns[si].imageUrl) { firstWithImg = groupRuns[si]; break; }
      }
      if (firstWithImg) {
        imgArea.appendChild(el("img", {
          class: "comfymodal-studio-exp-tile-single-img",
          src: firstWithImg.imageUrl,
          alt: "",
          loading: "lazy",
        }));
      }
    }

    // Time badge on bottom right
    var firstRunTime = firstRun.startedAt || "";
    if (firstRunTime) {
      var shortTime = firstRunTime.length > 16 ? firstRunTime.substring(11, 16) : firstRunTime;
      imgArea.appendChild(el("span", {
        class: "comfymodal-studio-exp-tile-time",
        text: shortTime,
      }));
    }

    card.appendChild(imgArea);
  }

  // Click handler — load the full experiment grid in Playground
  var _loading = false;
  card.addEventListener("click", async function () {
    if (_loading) return;
    _loading = true;
    card.style.opacity = "0.6";
    var result = await loadExperimentIntoPlayground(state, context, expId);
    _loading = false;
    if (!result || !result.ok) {
      // Restore tile and surface a concise error message
      card.style.opacity = "";
      var errEl = card.querySelector(".comfymodal-studio-exp-tile-error");
      if (!errEl) {
        errEl = el("div", {
          class: "comfymodal-studio-exp-tile-error",
          style: "font-size:9px;color:#f87171;padding:0 8px 4px;width:100%;box-sizing:border-box;",
          text: result && result.error ? result.error : "Failed to load experiment.",
        });
        card.appendChild(errEl);
      } else {
        errEl.textContent = result && result.error ? result.error : "Failed to load experiment.";
      }
    }
  });

  return card;
}

/**
 * Render a standalone experiment tile for a true Studio aggregate experiment
 * that has no associated cell runs yet. Shows the EXP badge, title, and status.
 * Click loads the experiment grid viewport in Playground.
 */
function _renderStandaloneExperimentTile(nr, apiBase, context, state) {
  var expId = nr.experimentId;
  var status = nr.status || "unknown";
  var titleText = "Experiment";

  var card = el("div", {
    class: "comfymodal-studio-history-card comfymodal-studio-experiment-tile"
      + (status === "completed" ? " completed" : "")
      + (status === "failed" || status === "error" ? " failed" : ""),
    tabindex: "0",
    role: "button",
    "data-expid": expId,
    "data-testid": "experiment-tile",
    "aria-label": "Open experiment " + expId + " in playground",
  });

  // Experiment badge
  var badgeRow = el("div", {
    style: "display:flex;align-items:center;gap:6px;padding:8px 8px 2px;width:100%;box-sizing:border-box;",
  });
  badgeRow.appendChild(el("span", {
    class: "comfymodal-studio-exp-tile-badge",
    text: "EXP",
    "aria-hidden": "true",
  }));
  badgeRow.appendChild(el("span", {
    class: "comfymodal-studio-exp-tile-title",
    text: titleText,
  }));
  card.appendChild(badgeRow);

  // Status
  var statusLine = el("div", {
    style: "display:flex;align-items:center;gap:6px;padding:0 8px;font-size:10px;width:100%;box-sizing:border-box;",
  });
  var statusColor = status === "completed" ? "#4ade80"
    : status === "failed" ? "#f87171"
    : status === "running" ? "#fbbf24" : "#888";
  statusLine.appendChild(el("span", {
    style: "color:" + statusColor + ";font-weight:600;text-transform:uppercase;",
    text: status,
  }));
  if (nr.totalCells) {
    statusLine.appendChild(el("span", {
      style: "color:#888;",
      text: "\u00b7 " + nr.totalCells + " cell" + (nr.totalCells !== 1 ? "s" : ""),
    }));
  }
  card.appendChild(statusLine);

  // Click handler — load experiment grid in Playground
  var _loading = false;
  card.addEventListener("click", async function () {
    if (_loading) return;
    _loading = true;
    card.style.opacity = "0.6";
    var result = await loadExperimentIntoPlayground(state, context, expId);
    _loading = false;
    if (!result || !result.ok) {
      card.style.opacity = "";
      var errEl = card.querySelector(".comfymodal-studio-exp-tile-error");
      if (!errEl) {
        errEl = el("div", {
          class: "comfymodal-studio-exp-tile-error",
          style: "font-size:9px;color:#f87171;padding:0 8px 4px;width:100%;box-sizing:border-box;",
          text: result && result.error ? result.error : "Failed to load experiment.",
        });
        card.appendChild(errEl);
      }
    }
  });

  return card;
}

// ── Group renderer ────────────────────────────────────────────────────────

function renderGroup(expId, groupRuns, apiBase, openPreview, columnCount) {
  var groupCard = el("div", {
    class: "comfymodal-studio-card",
    style: "margin-bottom:var(--space-md)",
  });

  var firstRun = groupRuns[0] || {};

  // ── Group header ────────────────────────────────────────────────────
  var groupHeader = el("div", {
    style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-sm);",
  });

  var groupTitle = el("strong");
  var featureId = firstRun.featureId || "";
  var presetId = firstRun.presetId || "";
  var presetLabel = firstRun.presetLabel || firstRun.presetId || "";
  if (featureId || presetId) {
    var featureLabel = featureId || "studio";
    var labelDisplay = presetLabel ? presetLabel.substring(0, 20) : "";
    groupTitle.textContent = "Studio " + featureLabel + (labelDisplay ? " \u2014 " + labelDisplay : "");
  } else {
    groupTitle.textContent = "Experiment: " + expId;
  }
  groupHeader.appendChild(groupTitle);

  // Stats
  var statsRow = el("div", {
    style: "display:flex;gap:8px;font-size:var(--font-size-xs);color:var(--color-text-muted);",
  });
  statsRow.appendChild(document.createTextNode(groupRuns.length + " run(s)"));
  var completedCount = groupRuns.filter(function (r) { return isCompleted(r); }).length;
  var failedCount = groupRuns.filter(function (r) { return isFailed(r); }).length;
  if (completedCount > 0) {
    statsRow.appendChild(el("span", {
      style: "color:var(--color-success, #4ade80)",
      text: "\u00b7 " + completedCount + " completed",
    }));
  }
  if (failedCount > 0) {
    statsRow.appendChild(el("span", {
      style: "color:var(--color-danger, #f87171)",
      text: "\u00b7 " + failedCount + " failed",
    }));
  }
  // Total from experiment metadata (canonical total when available, fallback loaded runs)
  var totalCells = firstRun.totalCells ?? groupRuns.length;
  if (totalCells > 0) {
    statsRow.appendChild(el("span", {
      style: "color:var(--color-text-muted)",
      text: "\u00b7 " + totalCells + " total",
    }));
  }
  groupHeader.appendChild(statsRow);
  groupCard.appendChild(groupHeader);

  // ── Gallery grid ───────────────────────────────────────────────────
  var gallery = renderHistoryGallery(groupRuns, apiBase, openPreview, columnCount);

  groupCard.appendChild(gallery);
  return groupCard;
}

// ── Run history status helpers (exported for reuse) ──────────────────────

export { isCompleted as isRunCompleted, isFailed as isRunFailed };
