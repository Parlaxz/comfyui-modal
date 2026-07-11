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

import { resolveRunImageUrl, hasRunImage, normalizeStudioRun } from "./studio-run-normalizer.js";
import { listRunHistory, updateRunAnnotation } from "./studio-backend-api.js";

// ── Element helper (local, matches other modules) ─────────────────────────

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
    } else if (k === "dataset") {
      Object.assign(e.dataset, props[k]);
    } else if (k === "disabled" || k === "checked" || k === "hidden" || k === "readonly" || k === "required") {
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

// ── Helpers ───────────────────────────────────────────────────────────────

function getRunExtra(run) {
  return (run && run.extra) || {};
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

// ── Favorite Star ─────────────────────────────────────────────────────────

function renderFavoriteStar(nr, apiBase) {
  var star = el("span", {
    class: "comfymodal-studio-favorite-star",
    "data-testid": "favorite-star",
    text: nr.favorite ? "\u2605" : "\u2606",
    style: "cursor:pointer;font-size:16px;color:" + (nr.favorite ? "#fbbf24" : "#555") + ";user-select:none;",
    title: nr.favorite ? "Remove from favorites" : "Add to favorites",
  });

  star.addEventListener("click", function (e) {
    e.stopPropagation();
    e.preventDefault();
    var wasFav = nr.favorite;
    var newFav = !wasFav;
    nr.favorite = newFav;
    var runId = nr.id || nr.experimentId;
    star.textContent = newFav ? "\u2605" : "\u2606";
    star.style.color = newFav ? "#fbbf24" : "#555";
    star.title = newFav ? "Remove from favorites" : "Add to favorites";

    updateRunAnnotation(apiBase, runId, { favorite: newFav }).then(function (result) {
      if (!result || result.status !== "ok") {
        nr.favorite = wasFav;
        star.textContent = wasFav ? "\u2605" : "\u2606";
        star.style.color = wasFav ? "#fbbf24" : "#555";
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

// ── Main renderer ─────────────────────────────────────────────────────────

export function renderHistory(state, context) {
  const container = el("div", { class: "comfymodal-studio-history" });
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // ── Internal state ──────────────────────────────────────────────────
  var queryParams = {
    limit: 50,
    offset: 0,
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
  var groupExperiments = false;
  var totalCount = 0;

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
    var typeOpts = ["", "run", "experiment", "experiment_cell"];
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
      onclick: function () {
        if (queryParams.offset > 0) {
          queryParams.offset = Math.max(0, queryParams.offset - queryParams.limit);
          fetchAndRender();
        }
      },
    });

    var nextBtn = el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "history-next",
      text: "Next \u2192",
      style: "font-size:10px;padding:2px 8px;",
      onclick: function () {
        queryParams.offset += queryParams.limit;
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
    bar.appendChild(prevBtn);
    bar.appendChild(nextBtn);
    bar.appendChild(pageInfo);

    // Update page info
    var currentPage = Math.floor(queryParams.offset / queryParams.limit) + 1;
    var totalPages = Math.ceil(totalCount / queryParams.limit) || 1;
    pageInfo.textContent = "Page " + currentPage + "/" + totalPages + " (" + totalCount + " total)";

    return bar;
  }

  // ── Preview Overlay ──────────────────────────────────────────────────
  function renderPreviewOverlay() {
    const existing = container.querySelector(".comfymodal-studio-history-preview");
    if (existing) existing.remove();
    if (!previewRun) return;

    const nr = previewRun;
    const imageUrl = nr.imageUrl;
    const rid = nr.id || "unknown";
    const status = nr.status;
    const promptText = (nr.prompt != null ? nr.prompt : rid).substring(0, 200);

    // Build metadata using normalized fields
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
    const seed = rc.seed != null ? rc.seed : (rqc.seed != null ? rqc.seed : "");
    if (seed !== "") metaItems.push({ label: "Seed", value: String(seed) });
    if (rc.steps != null) metaItems.push({ label: "Steps", value: String(rc.steps) });
    if (rc.cfg != null || rc.guidance != null) {
      metaItems.push({ label: "Guidance", value: String(rc.cfg != null ? rc.cfg : rc.guidance) });
    }
    if (rc.sampler_name || rc.sampler) metaItems.push({ label: "Sampler", value: String(rc.sampler_name || rc.sampler) });
    if (rc.scheduler) metaItems.push({ label: "Scheduler", value: String(rc.scheduler) });
    if (rc.denoise != null) metaItems.push({ label: "Denoise", value: String(rc.denoise) });
    if (rc.width && rc.height) metaItems.push({ label: "Size", value: rc.width + "\u00d7" + rc.height });
    if (nr.workflowHash) metaItems.push({ label: "Workflow", value: nr.workflowHash.substring(0, 8) + "\u2026" });
    if (nr.snapshotId) metaItems.push({ label: "Snapshot", value: nr.snapshotId.substring(0, 12) + "\u2026" });

    // Timing summary
    if (nr.timingSummary) {
      metaItems.push({ label: "Timing", value: nr.timingSummary });
    }

    const overlay = el("div", {
      class: "comfymodal-studio-history-preview",
      onclick: function (e) {
        if (e.target === overlay) {
          previewRun = null;
          renderPreviewOverlay();
        }
      },
    }, [
      el("div", { class: "comfymodal-studio-history-preview-backdrop" }),
      el("div", { class: "comfymodal-studio-history-preview-content" }, [
        el("button", {
          class: "comfymodal-studio-history-preview-close",
          text: "\u00d7",
          onclick: function () {
            previewRun = null;
            renderPreviewOverlay();
          },
        }),
        imageUrl
          ? el("img", {
              src: imageUrl,
              class: "comfymodal-studio-history-preview-image",
              alt: promptText,
            })
          : el("div", {
              class: "comfymodal-studio-history-preview-noimage",
              text: "No image available",
            }),
        el("div", { class: "comfymodal-studio-history-preview-info" }, [
          renderFavoriteStar(nr, apiBase),
          el("span", { class: "comfymodal-studio-history-preview-status", text: status }),
          el("span", { class: "comfymodal-studio-history-preview-prompt", text: promptText }),
        ]),
        // Generation settings metadata
        metaItems.length > 0
          ? el("div", { class: "comfymodal-studio-history-preview-meta" },
              metaItems.map(function (item) {
                return el("span", {
                  class: "comfymodal-studio-history-preview-meta-item",
                  text: item.label + ": " + item.value,
                });
              })
            )
          : null,
        // Note editor in preview
        renderNoteEditor(nr, apiBase),
      ]),
    ]);
    container.appendChild(overlay);
  }

  function openPreview(run) {
    previewRun = run;
    renderPreviewOverlay();
  }

  // ── Fetch and render ─────────────────────────────────────────────────
  function fetchAndRender() {
    // Clear
    while (container.firstChild) container.removeChild(container.firstChild);

    // Add filter bar
    container.appendChild(renderFilterBar());

    // Loading state
    container.appendChild(el("div", {
      class: "comfymodal-studio-card",
      text: "Loading history...",
    }));

    // Build query params for API
    var apiParams = {
      limit: queryParams.limit,
      offset: queryParams.offset,
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

    listRunHistory(apiBase, apiParams).then(function (data) {
      // Remove loading
      while (container.firstChild) container.removeChild(container.firstChild);

      // Re-add filter bar
      container.appendChild(renderFilterBar());

      if (!data) {
        container.appendChild(el("div", {
          class: "comfymodal-studio-card",
          style: "color:var(--color-danger)",
          text: "Failed to load history.",
        }));
        return;
      }

      var runs = data.runs || data.run_history || (Array.isArray(data) ? data : null);
      totalCount = data.total || (Array.isArray(runs) ? runs.length : 0);

      if (!runs || (Array.isArray(runs) && runs.length === 0)) {
        container.appendChild(el("div", {
          class: "comfymodal-studio-card",
          text: "No run history yet. Runs will appear here once you create experiments.",
        }));
        return;
      }

      var runList = Array.isArray(runs) ? runs : [];

      // Normalize all runs for consistent field access
      var normalizedRuns = runList.map(function (run) {
        return normalizeStudioRun(run, apiBase);
      }).filter(Boolean);

      if (groupExperiments) {
        // Group by experiment_id
        var grouped = {};
        var ungrouped = [];
        normalizedRuns.forEach(function (nr) {
          var expId = nr.experimentId || null;
          if (expId && expId !== "") {
            if (!grouped[expId]) grouped[expId] = [];
            grouped[expId].push(nr);
          } else {
            ungrouped.push(nr);
          }
        });

        // Render each group
        Object.entries(grouped).forEach(function (_ref) {
          var expId = _ref[0];
          var groupRuns = _ref[1];
          var groupEl = renderGroup(expId, groupRuns, apiBase, openPreview);
          container.appendChild(groupEl);
        });

        // Render ungrouped
        if (ungrouped.length > 0) {
          var fallbackId = "ungrouped_" + Date.now();
          var groupEl = renderGroup(fallbackId, ungrouped, apiBase, openPreview);
          container.appendChild(groupEl);
        }
      } else {
        // Ungrouped: render all runs flat
        normalizedRuns.forEach(function (nr) {
          var card = renderHistoryCard(nr, apiBase, openPreview);
          container.appendChild(card);
        });
      }
    }).catch(function (err) {
      while (container.firstChild) container.removeChild(container.firstChild);
      container.appendChild(renderFilterBar());
      var errorCard = el("div", { class: "comfymodal-studio-card" });
      errorCard.appendChild(el("p", {
        style: "color:var(--color-danger)",
        text: "Failed to load history: " + err.message,
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

// ── Group renderer ────────────────────────────────────────────────────────

function renderGroup(expId, groupRuns, apiBase, openPreview) {
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
  groupHeader.appendChild(statsRow);
  groupCard.appendChild(groupHeader);

  // ── Gallery grid ───────────────────────────────────────────────────
  var gallery = el("div", { class: "comfymodal-studio-history-gallery" });

  groupRuns.forEach(function (nr) {
    var card = renderHistoryCard(nr, apiBase, openPreview);
    gallery.appendChild(card);
  });

  groupCard.appendChild(gallery);
  return groupCard;
}

// ── Run history status helpers (exported for reuse) ──────────────────────

export { isCompleted as isRunCompleted, isFailed as isRunFailed };
