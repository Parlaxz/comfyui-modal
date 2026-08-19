// Modal Studio — History V2
//
// Feed page for the History V2 repository adapter.  Search, kind/status
// toggles, workflow/preset/date filters, sort, paginated sparse cards, and
// navigation into the generation detail overlay and the experiment detail
// page.  Everything renders through el() from studio-ui.js; no innerHTML
// with dynamic data, no framework imports.
//
// State is persisted through history-v2-view-state.js (load/save on every
// change).  Feed queries go through the repository adapter only, so the
// fixture/bridge implementation can be swapped later without touching this
// module.

import { el } from "./studio-ui.js";
import { createHistoryRepository, selectFeedAsset } from "./history-v2-repository.js";
import { loadHistoryViewState, saveHistoryViewState, DEFAULT_HIDDEN_STATUSES } from "./history-v2-view-state.js";
import { _formatDuration } from "./studio-run-normalizer.js";
import { renderGenerationDetail } from "./studio-history-v2-detail.js";
import { renderExperimentDetail } from "./studio-history-v2-experiment.js";

// ── Constants ─────────────────────────────────────────────────────────────

// Statuses that the status toggles never hide.
const ALWAYS_VISIBLE_STATUSES = ["completed", "running", "completed_with_failures"];
// Statuses with an explicit toggle button (Failed / Canceled / Interrupted).
const TOGGLE_STATUSES = ["failed", "canceled", "interrupted"];
const BOOL_FILTER_KEYS = ["favoriteOnly", "previewOnly", "originalAvailable", "hasImage"];

const PAGE_LIMIT = 24;

const STATUS_LABELS = {
  completed: "Completed",
  completed_with_failures: "Completed with failures",
  failed: "Failed",
  canceled: "Canceled",
  interrupted: "Interrupted",
  running: "Running",
};

const SORT_OPTIONS = [
  ["newest", "Newest first"],
  ["oldest", "Oldest first"],
  ["fastest", "Fastest"],
  ["slowest", "Slowest"],
  ["workflow_asc", "Workflow A-Z"],
  ["workflow_desc", "Workflow Z-A"],
];

// ── Small pure helpers ────────────────────────────────────────────────────

function _shortDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  try {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
      + ", " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch (err) {
    return String(iso);
  }
}

function _resultCountLabel(total) {
  if (total === 0) return "No results";
  return total === 1 ? "1 result" : total + " results";
}

function _statusChip(status) {
  const key = STATUS_LABELS[status] ? status : "running";
  const label = STATUS_LABELS[status] || status || "Running";
  return el("span", { class: "comfymodal-studio-history-v2-chip status-" + key, text: label });
}

export function selectGenerationFeedAsset(record) {
  const feat = record && record.featuredOutput ? record.featuredOutput : {};
  return selectFeedAsset(Object.assign({}, feat, {
    originalAvailable: !!(feat.originalAvailable || (record && record.originalAvailable)),
  }));
}

function _assetBadge(asset) {
  return asset && asset.kind === "preview"
    ? el("span", {
      class: "comfymodal-studio-history-v2-badge comfymodal-studio-history-v2-preview-badge",
      "data-testid": "history-v2-preview-badge",
      text: "Preview",
    })
    : null;
}

function _assetPlaceholder(asset, className) {
  return el("div", {
    class: (className || "comfymodal-studio-history-v2-noimage")
      + " comfymodal-studio-history-v2-asset-placeholder",
    "data-asset-kind": asset && asset.kind ? asset.kind : "none",
  }, [el("span", { text: asset && asset.label ? asset.label : "No image" })]);
}

// Build a card thumbnail container without ever selecting an Original URL.
function _cardThumb(output, alt, containerClass) {
  const cls = containerClass || "comfymodal-studio-history-v2-card-thumb";
  const asset = selectFeedAsset(output);
  if (!asset.url) {
    return _assetPlaceholder(asset, cls);
  }
  const container = el("div", { class: cls });
  container.appendChild(el("img", {
    class: "comfymodal-studio-history-v2-thumb-img",
    src: asset.url,
    alt: alt || "",
    loading: "lazy",
    onerror: function (e) {
      const imgEl = e.currentTarget;
      imgEl.style.display = "none";
      const parent = imgEl.parentNode;
      if (parent && !parent.querySelector(".comfymodal-studio-history-v2-noimage")) {
        parent.appendChild(_assetPlaceholder(asset));
      }
    },
  }));
  const badge = _assetBadge(asset);
  if (badge) container.appendChild(badge);
  return container;
}

// ── Main render entry point ───────────────────────────────────────────────

export function renderHistoryV2(state, context) {
  const root = el("div", {
    class: "comfymodal-studio-history-v2",
    "data-testid": "history-v2-page",
  });

  // ── Per-render state (fresh on every page mount, seeded from storage) ──
  const viewState = loadHistoryViewState();

  // Visible statuses: an explicitly saved set is honored exactly (a state
  // that excludes completed stays excluded); an empty set applies the
  // product defaults (failed + canceled hidden, interrupted visible).
  const storedStatuses = Array.isArray(viewState.filters.statuses)
    ? viewState.filters.statuses
    : [];
  let visibleStatuses = storedStatuses.length > 0
    ? new Set(storedStatuses)
    : defaultVisibleStatuses();

  let repo = null;
  let modeInfo = null;
  let facets = { workflows: [], presets: [] };
  let items = [];
  let total = 0;
  let nextCursor = null;
  let hasMore = false;
  let loading = true;
  let error = null;

  // Stale-async guard: every fetch bumps the token; responses from an
  // outdated token are ignored so rapid filter changes never interleave.
  let requestToken = 0;
  let searchTimer = null;

  // ── Toolbar element references (updated by refreshControls) ────────────
  let searchInput = null;
  let resultCountEl = null;
  let modeBannerEl = null;
  let sortSelect = null;
  let workflowSelect = null;
  let presetSelect = null;
  let dateFromInput = null;
  let dateToInput = null;
  const kindButtons = {};
  const statusButtons = {};
  const boolToggleEls = {};

  // ── Persistence ─────────────────────────────────────────────────────────
  function saveViewState() {
    saveHistoryViewState({
      search: viewState.search,
      filters: {
        kinds: Array.isArray(viewState.filters.kinds) ? viewState.filters.kinds.slice() : [],
        statuses: Array.from(visibleStatuses),
        workflow: viewState.filters.workflow,
        preset: viewState.filters.preset,
        favoriteOnly: !!viewState.filters.favoriteOnly,
        dateFrom: viewState.filters.dateFrom,
        dateTo: viewState.filters.dateTo,
        previewOnly: !!viewState.filters.previewOnly,
        originalAvailable: !!viewState.filters.originalAvailable,
        hasImage: !!viewState.filters.hasImage,
      },
      sort: viewState.sort,
    });
  }

  function defaultVisibleStatuses() {
    return new Set(
      ALWAYS_VISIBLE_STATUSES.concat(
        TOGGLE_STATUSES.filter(function (s) { return DEFAULT_HIDDEN_STATUSES.indexOf(s) === -1; })
      )
    );
  }

  function clearFilters() {
    if (searchTimer) { clearTimeout(searchTimer); searchTimer = null; }
    viewState.search = "";
    viewState.filters = {
      kinds: [], statuses: [], workflow: "", preset: "",
      favoriteOnly: false, dateFrom: "", dateTo: "",
      previewOnly: false, originalAvailable: false, hasImage: false,
    };
    visibleStatuses = defaultVisibleStatuses();
    viewState.sort = "newest";
    onViewChange();
  }

  // ── Facets ──────────────────────────────────────────────────────────────
  function mergeFacets(pageFacets) {
    if (!pageFacets || typeof pageFacets !== "object") return;
    const wf = new Set(facets.workflows);
    (pageFacets.workflows || []).forEach(function (w) { wf.add(w); });
    const ps = new Set(facets.presets);
    (pageFacets.presets || []).forEach(function (p) { ps.add(p); });
    facets = {
      workflows: Array.from(wf).sort(),
      presets: Array.from(ps).sort(),
    };
    refreshFacetSelects();
  }

  function refreshFacetSelects() {
    if (!workflowSelect || !presetSelect) return;
    const wfValue = viewState.filters.workflow || "";
    const presetValue = viewState.filters.preset || "";
    while (workflowSelect.firstChild) workflowSelect.removeChild(workflowSelect.firstChild);
    workflowSelect.appendChild(el("option", { value: "", text: "All workflows" }));
    (facets.workflows || []).forEach(function (w) {
      workflowSelect.appendChild(el("option", { value: w, text: w }));
    });
    workflowSelect.value = wfValue;
    while (presetSelect.firstChild) presetSelect.removeChild(presetSelect.firstChild);
    presetSelect.appendChild(el("option", { value: "", text: "All presets" }));
    (facets.presets || []).forEach(function (p) {
      presetSelect.appendChild(el("option", { value: p, text: p }));
    });
    presetSelect.value = presetValue;
  }

  // ── Feed fetching ───────────────────────────────────────────────────────
  async function fetchFeed(reset) {
    if (!repo) return;
    const token = ++requestToken;
    loading = true;
    error = null;
    if (reset) {
      items = [];
      total = 0;
      nextCursor = null;
      hasMore = false;
    }
    renderResults();

    const query = {
      limit: PAGE_LIMIT,
      cursor: reset ? null : nextCursor,
      search: viewState.search,
      kinds: Array.isArray(viewState.filters.kinds) ? viewState.filters.kinds.slice() : [],
      statuses: Array.from(visibleStatuses),
      workflow: viewState.filters.workflow,
      preset: viewState.filters.preset,
      favoriteOnly: !!viewState.filters.favoriteOnly,
      dateFrom: viewState.filters.dateFrom,
      // Include the whole end day for the date-range end (fixture compares ISO strings).
      dateTo: viewState.filters.dateTo ? viewState.filters.dateTo + "T23:59:59" : "",
      previewOnly: !!viewState.filters.previewOnly,
      originalAvailable: !!viewState.filters.originalAvailable,
      hasImage: !!viewState.filters.hasImage,
      sort: viewState.sort,
    };

    try {
      const page = await repo.listFeed(query);
      if (token !== requestToken) return; // stale response
      items = reset ? page.items : items.concat(page.items);
      total = page.total;
      nextCursor = page.nextCursor;
      hasMore = page.hasMore;
      mergeFacets(page.facets);
    } catch (err) {
      if (token !== requestToken) return;
      error = "Could not load history: " + ((err && err.message) || "unknown error");
    } finally {
      if (token === requestToken) {
        loading = false;
        renderResults();
        renderResultCount();
      }
    }
  }

  function onViewChange() {
    saveViewState();
    refreshControls();
    fetchFeed(true);
  }

  // ── Results area ────────────────────────────────────────────────────────
  const resultsEl = el("div", {
    class: "comfymodal-studio-history-v2-results",
    "data-testid": "history-v2-results",
  });

  function renderResultCount() {
    if (resultCountEl) resultCountEl.textContent = _resultCountLabel(total);
  }

  function renderResults() {
    while (resultsEl.firstChild) resultsEl.removeChild(resultsEl.firstChild);

    if (loading && items.length === 0) {
      resultsEl.appendChild(el("div", { class: "comfymodal-studio-history-v2-state", text: "Loading\u2026" }));
      return;
    }
    if (error && items.length === 0) {
      resultsEl.appendChild(errorStateEl());
      return;
    }
    if (items.length === 0) {
      resultsEl.appendChild(emptyStateEl());
      return;
    }

    const grid = el("div", { class: "comfymodal-studio-history-v2-grid" });
    items.forEach(function (record) {
      if (!record) return;
      if (record.kind === "experiment") {
        grid.appendChild(renderExperimentCard(record));
      } else {
        grid.appendChild(renderGenerationCard(record));
      }
    });
    resultsEl.appendChild(grid);

    if (hasMore) {
      resultsEl.appendChild(renderLoadMore());
    }
  }

  function emptyStateEl() {
    return el("div", { class: "comfymodal-studio-history-v2-state" }, [
      el("p", { class: "comfymodal-studio-history-v2-state-copy", text: "No history matches your filters" }),
      el("button", {
        class: "comfymodal-secondary-btn",
        type: "button",
        text: "Clear filters",
        onclick: function () { clearFilters(); },
      }),
    ]);
  }

  function errorStateEl() {
    return el("div", { class: "comfymodal-studio-history-v2-state" }, [
      el("p", { class: "comfymodal-studio-history-v2-state-error", text: error || "Could not load history" }),
      el("button", {
        class: "comfymodal-secondary-btn",
        type: "button",
        text: "Retry",
        onclick: function () { fetchFeed(true); },
      }),
    ]);
  }

  function renderLoadMore() {
    const btn = el("button", {
      class: "comfymodal-studio-history-v2-load-more",
      "data-testid": "history-v2-load-more",
      type: "button",
      text: loading ? "Loading\u2026" : "Load more",
      disabled: loading,
      onclick: function () {
        if (!loading) fetchFeed(false);
      },
    });
    return btn;
  }

  // ── Cards ───────────────────────────────────────────────────────────────
  function renderFavoriteStar(record) {
    const star = el("button", {
      type: "button",
      class: "comfymodal-studio-history-v2-fav",
      "data-testid": "history-v2-favorite-star",
      "aria-label": record.favorite ? "Remove from favorites" : "Add to favorites",
      "aria-pressed": record.favorite ? "true" : "false",
      title: record.favorite ? "Remove from favorites" : "Add to favorites",
      text: record.favorite ? "\u2605" : "\u2606",
    });
    star.addEventListener("click", function (e) {
      e.stopPropagation();
      e.preventDefault();
      if (star.disabled) return;
      const next = !record.favorite;
      star.disabled = true;
      repo.setFavorite(record.id, next).then(function () {
        record.favorite = next;
        star.disabled = false;
        star.textContent = next ? "\u2605" : "\u2606";
        star.setAttribute("aria-pressed", next ? "true" : "false");
        star.setAttribute("aria-label", next ? "Remove from favorites" : "Add to favorites");
      });
    });
    return star;
  }

  function _cardKeydown(e, handler) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handler();
    }
  }

  function renderGenerationCard(record) {
    const feat = record.featuredOutput || {};
    const metaParts = [];
    if (record.workflow) metaParts.push(record.workflow);
    if (record.preset) metaParts.push(record.preset);
    const metaText = metaParts.join(" \u00b7 ");
    const timeText = _shortDateTime(record.startedAt);
    const durText = record.durationMs != null ? _formatDuration(record.durationMs) : "";

    const card = el("div", {
      class: "comfymodal-studio-history-v2-card comfymodal-studio-history-v2-generation-card",
      "data-testid": "history-v2-generation-card",
      "data-id": record.id,
      tabindex: "0",
      role: "button",
      "aria-label": "Open generation " + (record.id || "") + (metaText ? " \u2014 " + metaText : ""),
      onclick: function () { openGeneration(record.id); },
      onkeydown: function (e) { _cardKeydown(e, function () { openGeneration(record.id); }); },
    }, [
      _cardThumb(Object.assign({}, feat, {
        originalAvailable: !!(feat.originalAvailable || record.originalAvailable),
      }), record.prompt || "Generation output"),
      el("div", { class: "comfymodal-studio-history-v2-card-top" }, [
        _statusChip(record.status),
        renderFavoriteStar(record),
      ]),
      record.prompt
        ? el("div", { class: "comfymodal-studio-history-v2-card-prompt", text: record.prompt })
        : null,
      metaText ? el("div", { class: "comfymodal-studio-history-v2-card-meta", text: metaText }) : null,
      el("div", { class: "comfymodal-studio-history-v2-card-foot" }, [
        timeText ? el("span", { class: "comfymodal-studio-history-v2-card-time", text: timeText }) : null,
        durText ? el("span", { class: "comfymodal-studio-history-v2-card-time", text: durText }) : null,
      ]),
    ]);
    return card;
  }

  function renderExperimentCard(record) {
    const cover = Array.isArray(record.cover) ? record.cover : [null, null, null, null];
    const coverGrid = el("div", { class: "comfymodal-studio-history-v2-cover" });
    cover.slice(0, 4).forEach(function (slot) {
      const asset = selectFeedAsset(slot);
      if (asset.url) {
        const slotEl = el("div", { class: "comfymodal-studio-history-v2-cover-slot" }, [
          el("img", {
            class: "comfymodal-studio-history-v2-thumb-img",
            src: asset.url,
            alt: "",
            loading: "lazy",
            onerror: function (e) {
              e.currentTarget.style.display = "none";
              if (e.currentTarget.parentNode) e.currentTarget.parentNode.appendChild(_assetPlaceholder(asset));
            },
          }),
        ]);
        const badge = _assetBadge(asset);
        if (badge) slotEl.appendChild(badge);
        coverGrid.appendChild(slotEl);
      } else {
        coverGrid.appendChild(_assetPlaceholder(
          asset,
          "comfymodal-studio-history-v2-cover-slot comfymodal-studio-history-v2-cover-empty",
        ));
      }
    });

    const count = record.resultCount != null ? record.resultCount : 0;
    const countsText = count + (count === 1 ? " result" : " results");
    const metaParts = [];
    if (record.workflow) metaParts.push(record.workflow);
    if (record.preset) metaParts.push(record.preset);
    const metaText = metaParts.join(" \u00b7 ");
    const timeText = _shortDateTime(record.startedAt);
    const durText = record.durationMs != null ? _formatDuration(record.durationMs) : "";

    const card = el("div", {
      class: "comfymodal-studio-history-v2-card comfymodal-studio-history-v2-experiment-card",
      "data-testid": "history-v2-experiment-card",
      "data-id": record.id,
      tabindex: "0",
      role: "button",
      "aria-label": "Open experiment " + (record.name || record.id || ""),
      onclick: function () { showExperiment(record.id); },
      onkeydown: function (e) { _cardKeydown(e, function () { showExperiment(record.id); }); },
    }, [
      coverGrid,
      el("div", { class: "comfymodal-studio-history-v2-card-top" }, [
        _statusChip(record.status),
        renderFavoriteStar(record),
      ]),
      el("div", { class: "comfymodal-studio-history-v2-card-name", text: record.name || record.id || "Experiment" }),
      el("div", { class: "comfymodal-studio-history-v2-card-counts", text: countsText }),
      metaText ? el("div", { class: "comfymodal-studio-history-v2-card-meta", text: metaText }) : null,
      el("div", { class: "comfymodal-studio-history-v2-card-foot" }, [
        timeText ? el("span", { class: "comfymodal-studio-history-v2-card-time", text: timeText }) : null,
        durText ? el("span", { class: "comfymodal-studio-history-v2-card-time", text: durText }) : null,
      ]),
    ]);
    return card;
  }

  // ── Detail navigation ───────────────────────────────────────────────────
  function openGeneration(id) {
    renderGenerationDetail(id, repo, {
      onClose: function () {
        // Focus returns to the shell page; nothing else to clean up.
      },
      onChanged: function () {
        // Refetch the first page so card state (favorite/note/featured)
        // stays truthful after detail-side mutations.
        fetchFeed(true);
      },
    });
  }

  function showExperiment(id) {
    while (root.firstChild) root.removeChild(root.firstChild);
    root.appendChild(el("div", { class: "comfymodal-studio-history-v2-state", text: "Loading\u2026" }));
    renderExperimentDetail(id, repo, {
      onBack: function () {
        renderFeedPage();
      },
      onChanged: function () {
        fetchFeed(true);
      },
    }).then(function (page) {
      while (root.firstChild) root.removeChild(root.firstChild);
      if (page) root.appendChild(page);
    }).catch(function () {
      while (root.firstChild) root.removeChild(root.firstChild);
      renderFeedPage();
    });
  }

  // Rebuild the whole feed page inside the same root container.
  function renderFeedPage() {
    while (root.firstChild) root.removeChild(root.firstChild);
    root.appendChild(renderToolbar());
    root.appendChild(resultsEl);
    refreshControls();
    renderResultCount();
    renderResults();
  }

  // ── Toolbar ─────────────────────────────────────────────────────────────
  function renderToolbar() {
    const toolbar = el("div", { class: "comfymodal-studio-history-v2-toolbar" });

    // Row 1: search, mode banner, result count, sort, clear all.
    const row1 = el("div", { class: "comfymodal-studio-history-v2-toolbar-row" });

    searchInput = el("input", {
      type: "search",
      class: "comfymodal-studio-history-v2-search",
      "data-testid": "history-v2-search",
      "aria-label": "Search history",
      placeholder: "Search history\u2026",
      value: viewState.search,
      oninput: function (e) {
        const value = e.currentTarget.value;
        if (searchTimer) clearTimeout(searchTimer);
        searchTimer = setTimeout(function () {
          viewState.search = value;
          onViewChange();
        }, 300);
      },
    });
    row1.appendChild(searchInput);

    modeBannerEl = el("span", {
      class: "comfymodal-studio-history-v2-mode-banner",
      "data-testid": "history-v2-mode-banner",
      text: "Demo data",
      hidden: true,
    });
    row1.appendChild(modeBannerEl);

    resultCountEl = el("span", {
      class: "comfymodal-studio-history-v2-result-count",
      "data-testid": "history-v2-result-count",
      "aria-live": "polite",
    });
    row1.appendChild(resultCountEl);

    sortSelect = el("select", {
      class: "comfymodal-studio-history-v2-select",
      "aria-label": "Sort history",
      onchange: function (e) {
        viewState.sort = e.currentTarget.value;
        onViewChange();
      },
    });
    SORT_OPTIONS.forEach(function (opt) {
      sortSelect.appendChild(el("option", { value: opt[0], text: opt[1] }));
    });
    row1.appendChild(sortSelect);

    row1.appendChild(el("button", {
      class: "comfymodal-studio-history-v2-clear-all",
      type: "button",
      text: "Clear all",
      onclick: function () { clearFilters(); },
    }));

    // Row 2: kind filter, status toggles, boolean toggles.
    const row2 = el("div", { class: "comfymodal-studio-history-v2-toolbar-row" });

    const kindGroup = el("div", {
      class: "comfymodal-studio-history-v2-toolbar-group",
      role: "group",
      "aria-label": "Filter by kind",
    });
    [["all", "All"], ["generation", "Generations"], ["experiment", "Experiments"]].forEach(function (entry) {
      const key = entry[0];
      const btn = el("button", {
        type: "button",
        class: "comfymodal-studio-history-v2-toggle",
        "data-kind": key,
        "aria-pressed": "false",
        text: entry[1],
        onclick: function () {
          viewState.filters.kinds = key === "all" ? [] : [key];
          onViewChange();
        },
      });
      kindButtons[key] = btn;
      kindGroup.appendChild(btn);
    });
    row2.appendChild(kindGroup);

    const statusGroup = el("div", {
      class: "comfymodal-studio-history-v2-toolbar-group",
      role: "group",
      "aria-label": "Filter by status",
    });
    TOGGLE_STATUSES.forEach(function (key) {
      const btn = el("button", {
        type: "button",
        class: "comfymodal-studio-history-v2-toggle",
        "data-status": key,
        "aria-pressed": "false",
        text: STATUS_LABELS[key] || key,
        onclick: function () {
          if (visibleStatuses.has(key)) {
            visibleStatuses.delete(key);
          } else {
            visibleStatuses.add(key);
          }
          onViewChange();
        },
      });
      statusButtons[key] = btn;
      statusGroup.appendChild(btn);
    });
    row2.appendChild(statusGroup);

    const BOOL_LABELS = {
      favoriteOnly: "Favorites only",
      previewOnly: "Preview only",
      originalAvailable: "Original available",
      hasImage: "Has image",
    };
    BOOL_FILTER_KEYS.forEach(function (key) {
      const btn = el("button", {
        type: "button",
        class: "comfymodal-studio-history-v2-toggle",
        "data-filter": key,
        "aria-pressed": "false",
        text: BOOL_LABELS[key] || key,
        onclick: function () {
          viewState.filters[key] = !viewState.filters[key];
          onViewChange();
        },
      });
      boolToggleEls[key] = btn;
      row2.appendChild(btn);
    });

    // Row 3: workflow, preset, date range.
    const row3 = el("div", { class: "comfymodal-studio-history-v2-toolbar-row" });

    workflowSelect = el("select", {
      class: "comfymodal-studio-history-v2-select",
      "aria-label": "Filter by workflow",
      onchange: function (e) {
        viewState.filters.workflow = e.currentTarget.value;
        onViewChange();
      },
    });
    presetSelect = el("select", {
      class: "comfymodal-studio-history-v2-select",
      "aria-label": "Filter by preset",
      onchange: function (e) {
        viewState.filters.preset = e.currentTarget.value;
        onViewChange();
      },
    });
    dateFromInput = el("input", {
      type: "date",
      class: "comfymodal-studio-history-v2-date",
      "aria-label": "From date",
      value: viewState.filters.dateFrom,
      onchange: function (e) {
        viewState.filters.dateFrom = e.currentTarget.value;
        onViewChange();
      },
    });
    dateToInput = el("input", {
      type: "date",
      class: "comfymodal-studio-history-v2-date",
      "aria-label": "To date",
      value: viewState.filters.dateTo,
      onchange: function (e) {
        viewState.filters.dateTo = e.currentTarget.value;
        onViewChange();
      },
    });

    row3.appendChild(el("span", { class: "comfymodal-studio-history-v2-toolbar-label", text: "Workflow" }));
    row3.appendChild(workflowSelect);
    row3.appendChild(el("span", { class: "comfymodal-studio-history-v2-toolbar-label", text: "Preset" }));
    row3.appendChild(presetSelect);
    row3.appendChild(el("span", { class: "comfymodal-studio-history-v2-toolbar-label", text: "From" }));
    row3.appendChild(dateFromInput);
    row3.appendChild(el("span", { class: "comfymodal-studio-history-v2-toolbar-label", text: "To" }));
    row3.appendChild(dateToInput);

    toolbar.appendChild(row1);
    toolbar.appendChild(row2);
    toolbar.appendChild(row3);
    return toolbar;
  }

  function refreshControls() {
    if (searchInput) searchInput.value = viewState.search;

    const kinds = Array.isArray(viewState.filters.kinds) ? viewState.filters.kinds : [];
    if (kindButtons.all) {
      kindButtons.all.setAttribute("aria-pressed", kinds.length === 0 ? "true" : "false");
    }
    if (kindButtons.generation) {
      kindButtons.generation.setAttribute("aria-pressed", kinds.indexOf("generation") !== -1 ? "true" : "false");
    }
    if (kindButtons.experiment) {
      kindButtons.experiment.setAttribute("aria-pressed", kinds.indexOf("experiment") !== -1 ? "true" : "false");
    }

    TOGGLE_STATUSES.forEach(function (key) {
      const btn = statusButtons[key];
      if (btn) btn.setAttribute("aria-pressed", visibleStatuses.has(key) ? "true" : "false");
    });

    BOOL_FILTER_KEYS.forEach(function (key) {
      const btn = boolToggleEls[key];
      if (btn) btn.setAttribute("aria-pressed", viewState.filters[key] ? "true" : "false");
    });

    if (workflowSelect) workflowSelect.value = viewState.filters.workflow || "";
    if (presetSelect) presetSelect.value = viewState.filters.preset || "";
    if (dateFromInput) dateFromInput.value = viewState.filters.dateFrom || "";
    if (dateToInput) dateToInput.value = viewState.filters.dateTo || "";
    if (sortSelect) sortSelect.value = viewState.sort || "newest";
    refreshFacetSelects();
  }

  // ── Mount ───────────────────────────────────────────────────────────────
  root.appendChild(renderToolbar());
  root.appendChild(resultsEl);
  refreshControls();
  renderResultCount();

  const mode =
    (context && context.historyMode)
    || (typeof window !== "undefined" ? window.__COMFYMODAL_HISTORY_MODE__ : null)
    || "auto";

  createHistoryRepository({
    mode: mode,
    apiBase: (context && context.apiBase) || "/comfymodal",
  }).then(function (r) {
    repo = r;
    modeInfo = (typeof r.getModeInfo === "function") ? r.getModeInfo() : null;
    if (modeBannerEl) {
      modeBannerEl.hidden = !(modeInfo && modeInfo.repository === "fixture");
    }
    if (typeof r.listFacets === "function") {
      r.listFacets().then(function (f) { mergeFacets(f); }).catch(function () {});
    }
    return fetchFeed(true);
  }).catch(function (err) {
    error = "Could not initialize history: " + ((err && err.message) || "unknown error");
    loading = false;
    renderResults();
  });

  return root;
}
