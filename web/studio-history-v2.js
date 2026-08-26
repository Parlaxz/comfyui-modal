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

import { el, renderEmptyState } from "./studio-ui.js";
import { renderLoadingState } from "./studio-loading.js";
import { createHistoryRepository, selectFeedAsset } from "./history-v2-repository.js";
import { subscribeStudioSync } from "./studio-sync.js";
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

// ── Cross-page record focus (H13) ─────────────────────────────────────────
//
// One-shot in-memory navigation request: another page (Playground recent-runs
// filmstrip) can ask the NEXT History mount to open a specific durable record
// instead of the feed.  No URL routing, no persistence — the request is
// consumed exactly once by renderHistoryV2 and silently dropped when the
// record no longer resolves (the History page then renders normally).
let _pendingRecordFocus = null;

export function requestHistoryRecordFocus(recordId, kind) {
  _pendingRecordFocus = {
    id: String(recordId == null ? "" : recordId),
    kind: kind === "generation" ? "generation" : "experiment",
  };
}

function _consumeRecordFocus() {
  const focus = _pendingRecordFocus;
  _pendingRecordFocus = null;
  return focus && focus.id ? focus : null;
}

// ── Grid columns setting (Settings → History → Grid columns) ──────────────
// History V2 is the consuming surface for this modern setting.  The value is
// read once per mount, normalized, and applied as an inline CSS custom
// property on the page root; the feed grid resolves its track count from it
// (see studio-styles.js).  The shell re-renders the active page on every tab
// activation, so a change made in Settings applies when the user returns to
// History without a browser reload.  Presentation only: no view-state,
// filter, pagination, or favorite code path consults it.
export const HISTORY_COLUMNS_KEY = "comfymodal-studio-history-columns";
export const HISTORY_COLUMNS_MIN = 2;
export const HISTORY_COLUMNS_MAX = 8;
export const HISTORY_COLUMNS_DEFAULT = 6;

// Canonical normalization with the same semantics as the Settings control:
// parseInt truncation (Settings reads with parseInt), NaN/empty/corrupt →
// default 6, then clamp to [2, 8].  Malformed persisted state can never
// break History rendering.
export function normalizeHistoryColumns(raw) {
  const n = parseInt(raw, 10);
  if (isNaN(n)) return HISTORY_COLUMNS_DEFAULT;
  if (n < HISTORY_COLUMNS_MIN) return HISTORY_COLUMNS_MIN;
  if (n > HISTORY_COLUMNS_MAX) return HISTORY_COLUMNS_MAX;
  return n;
}

function _readStoredColumns() {
  try {
    if (typeof localStorage === "undefined" || !localStorage) return null;
    return localStorage.getItem(HISTORY_COLUMNS_KEY);
  } catch (err) {
    return null; // corrupt/unavailable storage → default columns
  }
}

const STATUS_LABELS = {
  completed: "Completed",
  completed_with_failures: "Completed with failures",
  failed: "Failed",
  canceled: "Canceled",
  interrupted: "Interrupted",
  running: "Running",
};

// Shared chip tones (I3 taxonomy): STATUS → data-tone.  Legacy status-*
// classes stay verbatim; the tone recolors nothing that the legacy rules
// already decide — meaning never changes.
const STATUS_TONES = {
  completed: "ok",
  completed_with_failures: "warn",
  failed: "error",
  canceled: "neutral",
  interrupted: "warn",
  running: "running",
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
  return el("span", {
    class: "comfymodal-studio-history-v2-chip status-" + key + " cm-chip",
    "data-tone": STATUS_TONES[key] || "neutral",
    text: label,
  });
}

// ── Page heading (I1 §3.3 / I2 shell h1) ──────────────────────────────────
//
// Truthful page-level h2 under the shell h1.  History has no visible page
// title, so the heading is accessible-visually-hidden with the clip
// pattern — never display:none / visibility:hidden / hidden.  Inline local
// style only; shared styles are not edited by this lane.

const PAGE_TITLE_OFFSCREEN_STYLE =
  "position:absolute;width:1px;height:1px;margin:-1px;padding:0;" +
  "border:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;";

function _pageHeading() {
  return el("h2", {
    class: "comfymodal-studio-history-v2-page-title",
    "data-testid": "history-v2-page-title",
    text: "History",
    style: PAGE_TITLE_OFFSCREEN_STYLE,
  });
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
  // Presentation-only setting read at mount (see HISTORY_COLUMNS_KEY).
  const gridColumns = normalizeHistoryColumns(_readStoredColumns());
  const root = el("div", {
    class: "comfymodal-studio-history-v2",
    "data-testid": "history-v2-page",
    "data-grid-columns": String(gridColumns),
    style: "--comfymodal-studio-history-columns: " + gridColumns,
  });
  let historyStale = false;
  let unsubscribeHistorySync = null;

  function refreshFromSync() {
    if (!root.isConnected) {
      if (unsubscribeHistorySync) unsubscribeHistorySync();
      unsubscribeHistorySync = null;
      return;
    }
    historyStale = true;
    root.dataset.syncStale = "true";
    if (repo) {
      fetchFeed(true).finally(function () {
        historyStale = false;
        root.dataset.syncStale = "false";
      });
    }
  }

  unsubscribeHistorySync = subscribeStudioSync("history", refreshFromSync);

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
      resultsEl.appendChild(renderLoadingState({
        label: "Loading history\u2026",
        size: "page",
        testid: "history-v2-loading",
      }));
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
    return renderEmptyState({
      title: "No history matches your filters",
      action: el("button", {
        class: "comfymodal-secondary-btn",
        type: "button",
        text: "Clear filters",
        onclick: function () { clearFilters(); },
      }),
      testid: "history-v2-empty",
    });
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
  // Durable-first favorite toggle shared by generation and experiment feed
  // cards.  The glyph flips only after the server acknowledges the PATCH; a
  // rejected request restores the prior durable state, re-enables the star,
  // and surfaces a bounded truthful error via the existing action-note
  // pattern — never an unhandled rejection and never a stranded control.
  //
  // Accessible names carry record context (I1 §3.1 duplicate-label fix): all
  // simultaneously visible stars must be distinguishable.  Short id tails
  // keep names unique without exposing full UUIDs.
  function _favoriteAccessibleName(rec, favorite) {
    const isExperiment = !!(rec && rec.kind === "experiment");
    const kind = isExperiment ? "experiment" : "generation";
    const idTail = String((rec && rec.id) == null ? "" : rec.id).slice(-6);
    const namePart = isExperiment && rec && rec.name ? String(rec.name) : "";
    const timePart = namePart ? "" : _shortDateTime(rec && rec.startedAt);
    let context = "";
    if (namePart && idTail) context = namePart + " (" + idTail + ")";
    else if (namePart) context = namePart;
    else if (timePart && idTail) context = timePart + " (" + idTail + ")";
    else if (timePart) context = timePart;
    else if (idTail) context = idTail;
    return (favorite ? "Remove " : "Add ") + kind +
      (context ? " " + context : "") +
      (favorite ? " from favorites" : " to favorites");
  }

  function renderFavoriteStar(record) {
    const wrap = el("span", { class: "comfymodal-studio-history-v2-fav-wrap" });
    const note = el("span", {
      class: "comfymodal-studio-history-v2-action-note",
      role: "status",
      "aria-live": "polite",
    });
    function paint(value) {
      star.textContent = value ? "\u2605" : "\u2606";
      star.setAttribute("aria-pressed", value ? "true" : "false");
      star.setAttribute("aria-label", _favoriteAccessibleName(record, value));
      star.title = _favoriteAccessibleName(record, value);
    }
    const star = el("button", {
      type: "button",
      class: "comfymodal-studio-history-v2-fav",
      "data-testid": "history-v2-favorite-star",
      "aria-label": _favoriteAccessibleName(record, !!record.favorite),
      "aria-pressed": record.favorite ? "true" : "false",
      title: _favoriteAccessibleName(record, !!record.favorite),
      text: record.favorite ? "\u2605" : "\u2606",
    });
    star.addEventListener("click", function (e) {
      e.stopPropagation();
      e.preventDefault();
      if (star.disabled) return;
      const prior = !!record.favorite;
      const next = !prior;
      star.disabled = true;
      note.textContent = "";
      repo.setFavorite(record.id, next).then(function (ack) {
        record.favorite = ack && typeof ack.favorite === "boolean" ? ack.favorite : next;
        paint(record.favorite);
        star.disabled = false;
      }).catch(function () {
        record.favorite = prior;
        paint(prior);
        note.textContent = "Favorite failed";
        star.disabled = false;
      });
    });
    wrap.appendChild(star);
    wrap.appendChild(note);
    return wrap;
  }

  function _cardKeydown(e, handler) {
    if (e.key === "Enter" || e.key === " ") {
      // Interactive controls inside the card keep their native activation:
      // Enter/Space on an inner button toggles THAT control, never opens the
      // card.
      if (e.target && e.target.closest && e.target.closest("button, input, select, textarea")) return;
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
        // Route truth (I9A): closing a focused detail drops the stale focus
        // identity from the URL through the shell's routing authority, so a
        // cached reopen or reload cannot resurrect the dismissed record.
        if (typeof context.clearRouteFocus === "function") context.clearRouteFocus();
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
    root.appendChild(renderLoadingState({
      label: "Loading experiment\u2026",
      size: "page",
      testid: "history-v2-experiment-loading",
    }));
    renderExperimentDetail(id, repo, {
      onBack: function () {
        renderFeedPage();
      },
      onChanged: function () {
        fetchFeed(true);
      },
    }).then(function (page) {
      while (root.firstChild) root.removeChild(root.firstChild);
      if (page) {
        root.appendChild(page);
        // Focus-in for the experiment sub-page (the page-swap analog of the
        // generation detail overlay's focus-in): the first enabled control
        // is Back to history — on the not-found placeholder it is the same
        // back action.
        var firstBtn = page.querySelector("button:not([disabled])");
        if (firstBtn && typeof firstBtn.focus === "function") firstBtn.focus();
      }
    }).catch(function () {
      renderFeedPage();
    });
  }

  // Rebuild the whole feed page inside the same root container.  Only
  // reached after an experiment sub-page (back navigation or load failure),
  // so returning focus to Search restores a deterministic keyboard anchor
  // instead of dropping focus to <body>.
  function renderFeedPage() {
    while (root.firstChild) root.removeChild(root.firstChild);
    root.appendChild(_pageHeading());
    root.appendChild(renderToolbar());
    root.appendChild(resultsEl);
    refreshControls();
    renderResultCount();
    renderResults();
    if (searchInput && typeof searchInput.focus === "function") searchInput.focus();
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
  root.appendChild(_pageHeading());
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
    // H13: a pending cross-page focus request (e.g. Playground filmstrip
    // experiment click) opens the durable record directly.  Experiment
    // detail replaces the feed page entirely; generation detail overlays it.
    // showExperiment falls back to the feed page on lookup failure.
    var focus = _consumeRecordFocus();
    if (focus && focus.kind === "experiment") {
      showExperiment(focus.id);
      return null;
    }
    var initialFeed = fetchFeed(true);
    if (focus) openGeneration(focus.id);
    return initialFeed;
  }).catch(function (err) {
    error = "Could not initialize history: " + ((err && err.message) || "unknown error");
    loading = false;
    renderResults();
  });

  return root;
}
