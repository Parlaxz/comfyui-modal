// Modal Studio — History V2 Repository Adapter
//
// Narrow adapter interface for the History V2 feed.  Every frontend module
// depends only on the repository object returned here, so implementations
// can be swapped without touching callers.
//
// Modes:
//   - "auto"    (default) → real History V2 backend HTTP ({apiBase}/history-v2/*)
//   - "v2"      → real History V2 backend HTTP, identical to "auto"
//   - "fixture" → deterministic in-memory dataset (history-v2-fixtures.js);
//                 explicit dev/test use only — never chosen by "auto"
//   - "bridge"  → maps the contract onto the CURRENT legacy endpoints;
//                 explicit legacy use only
//
// "auto" / "v2" NEVER fall back to demo data.  A real backend failure is
// surfaced truthfully: listFeed rejects (the UI renders the load error) and
// detail lookups resolve to records carrying a "load_failed" error.  The
// fixture/bridge implementations are retained for explicit opt-in only.
//
// NOTE: createHistoryRepository returns a Promise<repository> so every mode
// is consumed uniformly.
//
// No rendering logic — pure data access.  Fixture/bridge methods resolve to
// safe defaults; v2 methods reject (or mark load_failed) so real failures
// are visible instead of silently showing demo data.

import { createFixtureRepository } from "./history-v2-fixtures.js";

// ── Public constants ─────────────────────────────────────────────────────

export const HISTORY_V2_MODES = ["auto", "fixture", "bridge", "v2"];

// ── Module-level cache ───────────────────────────────────────────────────

// Keyed by `mode + "\n" + apiBase`; stores the Promise so concurrent
// callers always receive the SAME repository instance.
const _repositoryCache = new Map();

// ── Canonical status sets / aliases ─────────────────────────────────────

// Canonical frontend/wire status values (generations never carry
// completed_with_failures; experiments can).  Older internal aliases
// ("success", "partial") are normalized away at every boundary.
const GENERATION_STATUSES = ["completed", "failed", "canceled", "interrupted", "running"];
const EXPERIMENT_STATUSES = ["completed", "failed", "canceled", "interrupted", "running", "completed_with_failures"];

const STATUS_ALIASES = {
  "completed": "completed",
  "complete": "completed",
  "success": "completed",
  "succeeded": "completed",
  "successful": "completed",
  "done": "completed",
  "ok": "completed",
  "finished": "completed",
  "failed": "failed",
  "failure": "failed",
  "error": "failed",
  "errored": "failed",
  "canceled": "canceled",
  "cancelled": "canceled",
  "cancel": "canceled",
  "interrupted": "interrupted",
  "aborted": "interrupted",
  "abort": "interrupted",
  "stopped": "interrupted",
  "running": "running",
  "pending": "running",
  "queued": "running",
  "in_progress": "running",
  "processing": "running",
  "active": "running",
  "partial": "completed_with_failures",
  "completed_with_failures": "completed_with_failures",
};

/**
 * Normalize a list of status filter values to canonical wire statuses.
 * Unknown / obsolete aliases are dropped (never forwarded); duplicates are
 * removed while preserving first-seen order.
 * @param {Array} [statuses]
 * @returns {string[]} canonical statuses
 */
export function normalizeStatuses(statuses) {
  const out = [];
  if (!Array.isArray(statuses)) return out;
  statuses.forEach(function (s) {
    if (s == null) return;
    const key = String(s).toLowerCase().replace(/\s+/g, "_");
    const mapped = STATUS_ALIASES[key];
    if (mapped && out.indexOf(mapped) === -1) out.push(mapped);
  });
  return out;
}

// ── createHistoryRepository ──────────────────────────────────────────────

/**
 * Create (or return the cached) History V2 repository.
 * @param {object} [opts]
 * @param {"auto"|"fixture"|"bridge"|"v2"} [opts.mode="auto"]
 * @param {string} [opts.apiBase="/comfymodal"]
 * @returns {Promise<object>} repository object (contract below)
 */
export function createHistoryRepository(opts) {
  const o = opts || {};
  const mode = HISTORY_V2_MODES.indexOf(o.mode) !== -1 ? o.mode : "auto";
  const apiBase = o.apiBase || "/comfymodal";
  const key = mode + "\n" + apiBase;
  if (_repositoryCache.has(key)) return _repositoryCache.get(key);
  const promise = _resolveRepository(mode, apiBase);
  _repositoryCache.set(key, promise);
  return promise;
}

function _resolveRepository(mode, apiBase) {
  if (mode === "fixture") {
    return Promise.resolve(createFixtureRepository());
  }
  if (mode === "bridge") {
    return Promise.resolve(_createBridgeRepository(apiBase));
  }
  // "auto" (default) and "v2" both use the real History V2 backend.  auto no
  // longer probes or falls back to fixtures — a real backend failure surfaces
  // as a truthful load error instead of silently showing demo data.
  return Promise.resolve(_createV2Repository(apiBase));
}

// Probe GET {apiBase}/history?page=1&page_size=1 with a ~1500ms timeout.
// Resolves true only on an HTTP ok response; every other outcome (404,
// network error, timeout) resolves false so we fall back to the fixture.
function _probeHistoryEndpoint(apiBase) {
  return new Promise(function (resolve) {
    let controller = null;
    try {
      controller = new AbortController();
    } catch (err) {
      controller = null;
    }
    const timer = setTimeout(function () {
      if (controller) controller.abort();
      resolve(false);
    }, 1500);
    const url = apiBase + "/history?page=1&page_size=1";
    fetch(url, { signal: controller ? controller.signal : undefined })
      .then(function (res) {
        clearTimeout(timer);
        resolve(!!(res && res.ok));
      })
      .catch(function () {
        clearTimeout(timer);
        resolve(false);
      });
  });
}

// ── Normalizer (exported for tests and shared by all implementations) ───

/**
 * Normalize a raw feed record into a GenerationRecord or ExperimentRecord.
 * Kind detection: raw.kind === "experiment" | "studio_experiment" |
 * raw.experiment_id → experiment; otherwise generation.
 * @param {object|null|undefined} raw
 * @returns {object} GenerationRecord | ExperimentRecord (all fields present)
 */
export function normalizeFeedItem(raw) {
  if (!raw || typeof raw !== "object") return _emptyGenerationRecord();
  if (_isExperimentRaw(raw)) return _normalizeExperiment(raw);
  return _normalizeGeneration(raw);
}

export function normalizeHistoryOutput(raw, index) {
  const out = raw && typeof raw === "object" ? raw : {};
  return {
    index: out.index != null ? out.index : (index != null ? index : 0),
    outputId: _firstString(out.output_id, out.outputId, out.id),
    assetId: _firstString(out.asset_id, out.assetId),
    thumbUrl: _firstString(out.thumb_url, out.thumbUrl),
    previewUrl: _firstString(out.preview_url, out.previewUrl),
    originalUrl: _firstString(out.original_url, out.originalUrl),
    originalFailed: _toBool(out.original_failed, _toBool(out.originalFailed, false)),
    originalAvailable: _toBool(out.original_available, _toBool(out.originalAvailable, false)),
    status: _firstString(out.status, "success"),
  };
}

export function selectFeedAsset(output) {
  const out = output && typeof output === "object" ? output : {};
  if (out.thumbUrl) return { kind: "thumbnail", url: out.thumbUrl, label: "Thumbnail" };
  if (out.previewUrl) return { kind: "preview", url: out.previewUrl, label: "Preview" };
  if (out.originalUrl || out.originalAvailable) return { kind: "original", url: "", label: "Original available" };
  if (out.originalFailed) return { kind: "original-failed", url: "", label: "Original generation failed" };
  return { kind: "none", url: "", label: "No image" };
}

export function selectDetailAsset(output) {
  const out = output && typeof output === "object" ? output : {};
  if (out.previewUrl) return { kind: "preview", url: out.previewUrl, label: "Preview" };
  if (out.thumbUrl) return { kind: "thumbnail", url: out.thumbUrl, label: "Thumbnail" };
  if (out.originalUrl || out.originalAvailable) return { kind: "original", url: "", label: "Original available" };
  if (out.originalFailed) return { kind: "original-failed", url: "", label: "Original generation failed" };
  return { kind: "none", url: "", label: "No image" };
}

export function normalizeHistoryAttempt(raw) {
  const attempt = raw && typeof raw === "object" ? raw : {};
  return {
    status: _firstString(attempt.status),
    startedAt: _firstString(attempt.started_at, attempt.startedAt),
    durationMs: _toIntOrNull(attempt.duration_ms != null ? attempt.duration_ms : attempt.durationMs),
    error: attempt.error || null,
    mode: _firstString(attempt.mode, attempt.purpose),
    runId: _firstString(attempt.run_id, attempt.runId),
  };
}

export function normalizeHistoryAttempts(raw) {
  return (Array.isArray(raw) ? raw : []).map(normalizeHistoryAttempt);
}

function _isExperimentRaw(raw) {
  return raw.kind === "experiment"
    || raw.kind === "studio_experiment"
    || !!raw.experiment_id;
}

// ── Generation normalization ────────────────────────────────────────────

function _normalizeGeneration(raw) {
  const extra = raw.extra && typeof raw.extra === "object" ? raw.extra : {};
  const outputs = Array.isArray(raw.outputs) ? raw.outputs : [];
  const annotations = _extractAnnotations(raw, extra);

  const outputCount = _toInt(raw.output_count, outputs.length);
  const previewOnly = _toBool(raw.preview_only, _toBool(extra.preview_only, false));
  const status = _coerceStatus(raw.status, GENERATION_STATUSES, "running");

  return {
    id: _firstString(raw.id, raw.run_id, raw.runId),
    kind: "generation",
    status: status,
    workflow: _firstString(raw.workflow, raw.workflow_name, extra.workflow_name, extra.workflow),
    workflowVersion: _firstString(raw.workflow_version, raw.workflowVersion),
    preset: _firstString(raw.preset, raw.preset_id, raw.preset_label, extra.studio_preset_label, extra.studio_preset_id, extra.preset),
    prompt: _firstString(raw.prompt, extra.prompt),
    negativePrompt: _firstString(raw.negative_prompt, raw.negativePrompt, extra.negative_prompt),
    startedAt: _firstString(raw.started_at, raw.created_at, raw.timestamp, raw.created, raw.startedAt),
    completedAt: _firstString(raw.completed_at, raw.completedAt),
    durationMs: _toDurationMs(raw),
    favorite: annotations.favorite,
    note: annotations.note,
    tags: _stringArray(raw.tags, extra.tags),
    models: _stringArray(raw.models, extra.models),
    outputCount: outputCount,
    hasImage: _hasImage(raw, outputs),
    previewOnly: previewOnly,
    originalAvailable: _toBool(raw.original_available, _toBool(extra.original_available,
      outputs.some(function (out) { return !!normalizeHistoryOutput(out).originalUrl; }))),
    featuredOutput: _featuredOutput(raw, outputs),
    runId: _firstString(raw.run_id, raw.runId, raw.id),
  };
}

// ── Experiment normalization ────────────────────────────────────────────

function _normalizeExperiment(raw) {
  const extra = raw.extra && typeof raw.extra === "object" ? raw.extra : {};
  const cells = Array.isArray(raw.cells) ? raw.cells : [];
  const annotations = _extractAnnotations(raw, extra);
  const axisLabels = raw.axis_labels && typeof raw.axis_labels === "object"
    ? raw.axis_labels
    : (raw.axes && typeof raw.axes === "object" ? raw.axes : { x: "", y: "" });

  return {
    id: _firstString(raw.id, raw.experiment_id, raw.run_id),
    kind: "experiment",
    name: _firstString(raw.name, raw.experiment_name, raw.title, raw.id),
    status: _coerceStatus(raw.status, EXPERIMENT_STATUSES, "running"),
    workflow: _firstString(raw.workflow, raw.workflow_name, extra.workflow_name, extra.workflow),
    preset: _firstString(raw.preset, raw.preset_id, raw.preset_label, extra.studio_preset_label, extra.studio_preset_id, extra.preset),
    prompt: _firstString(raw.prompt, extra.prompt),
    startedAt: _firstString(raw.started_at, raw.created_at, raw.timestamp, raw.startedAt),
    completedAt: _firstString(raw.completed_at, raw.completedAt),
    durationMs: _toDurationMs(raw),
    favorite: annotations.favorite,
    note: annotations.note,
    tags: _stringArray(raw.tags, extra.tags),
    models: _stringArray(raw.models, extra.models),
    trueCellCount: _toInt(raw.true_cell_count, _toInt(raw.cell_count, cells.length)),
    resultCount: _toInt(raw.result_count, _countCells(cells, ["success"])),
    failedCount: _toInt(raw.failed_count, _countCells(cells, ["failed"])),
    interruptedCount: _toInt(raw.interrupted_count, _countCells(cells, ["interrupted", "canceled"])),
    axisLabels: {
      x: _firstString(axisLabels.x, axisLabels.x_label),
      y: _firstString(axisLabels.y, axisLabels.y_label),
    },
    cover: _coverFromCells(cells),
  };
}

// Position-stable 2x2 cover: first 4 cells in cell order, padded to 4 slots
// with null (null = empty block).
function _coverFromCells(cells) {
  const cover = (cells || []).slice(0, 4).map(function (c) {
    const cell = c && typeof c === "object" ? c : {};
    const cellOutputs = Array.isArray(cell.outputs) ? cell.outputs : [];
    const featuredIndex = cell.featured_output_index != null ? cell.featured_output_index : 0;
    const output = cellOutputs.length > 0
      ? normalizeHistoryOutput(cellOutputs[featuredIndex] || cellOutputs[0], featuredIndex)
      : normalizeHistoryOutput(cell, cell.index);
    return {
      thumbUrl: output.thumbUrl,
      previewUrl: output.previewUrl,
      originalUrl: output.originalUrl,
      originalFailed: output.originalFailed,
      originalAvailable: output.originalAvailable,
      cellKey: cell.key || cell.cell_id || "",
    };
  });
  while (cover.length < 4) cover.push(null);
  return cover;
}

// ── Small nil-safe helpers ──────────────────────────────────────────────

function _extractAnnotations(raw, extra) {
  let annotations = raw.annotations && typeof raw.annotations === "object"
    ? raw.annotations
    : (extra.annotations && typeof extra.annotations === "object" ? extra.annotations : {});
  if (!annotations || typeof annotations !== "object") annotations = {};
  const favorite = annotations.favorite != null ? annotations.favorite : raw.favorite;
  const note = annotations.note != null ? annotations.note : raw.note;
  return { favorite: !!favorite, note: note != null ? String(note) : "" };
}

function _coerceStatus(raw, canonical, fallback) {
  const value = raw != null ? String(raw) : "";
  const key = value.toLowerCase().replace(/\s+/g, "_");
  const mapped = STATUS_ALIASES[key] || key;
  if (canonical.indexOf(mapped) !== -1) return mapped;
  return fallback;
}

function _toDurationMs(raw) {
  const extra = raw.extra && typeof raw.extra === "object" ? raw.extra : {};
  if (raw.duration_ms != null) return _toIntOrNull(raw.duration_ms);
  if (raw.durationMs != null) return _toIntOrNull(raw.durationMs);
  if (extra.duration_ms != null) return _toIntOrNull(extra.duration_ms);
  const timings = raw.timings && typeof raw.timings === "object" ? raw.timings : {};
  if (timings.end_to_end_total_ms != null) return _toIntOrNull(timings.end_to_end_total_ms);
  if (raw.duration != null && typeof raw.duration === "number") return Math.round(raw.duration * 1000);
  return null;
}

function _toIntOrNull(v) {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : parseInt(v, 10);
  if (typeof n !== "number" || isNaN(n)) return null;
  return n;
}

function _toInt(v, fallback) {
  const n = _toIntOrNull(v);
  return n != null ? n : (fallback != null ? fallback : 0);
}

function _toBool(v, fallback) {
  if (typeof v === "boolean") return v;
  if (v === "true" || v === "1") return true;
  if (v === "false" || v === "0" || v === "") return false;
  return fallback != null ? fallback : false;
}

function _firstString() {
  for (let i = 0; i < arguments.length; i++) {
    const v = arguments[i];
    if (v != null && v !== "") return String(v);
  }
  return "";
}

function _stringArray() {
  const out = [];
  for (let i = 0; i < arguments.length; i++) {
    const src = arguments[i];
    if (!Array.isArray(src)) continue;
    src.forEach(function (v) {
      if (v == null) return;
      const s = typeof v === "object" ? (v.name || v.model || v.label || "") : String(v);
      if (s && out.indexOf(s) === -1) out.push(s);
    });
  }
  return out;
}

function _countCells(cells, statuses) {
  let n = 0;
  cells.forEach(function (c) {
    if (c && statuses.indexOf(c.status) !== -1) n++;
  });
  return n;
}

function _hasImage(raw, outputs) {
  if (raw.has_image != null) return _toBool(raw.has_image, false);
  if (raw.hasImage != null) return _toBool(raw.hasImage, false);
  for (let i = 0; i < outputs.length; i++) {
    const o = outputs[i] || {};
    if (o.thumb_url || o.preview_url || o.image_url || o.thumbUrl || o.previewUrl || o.asset_id) return true;
  }
  return outputs.length > 0;
}

function _featuredOutput(raw, outputs) {
  const rawFeat = raw.featured_output && typeof raw.featured_output === "object" ? raw.featured_output : null;
  let index = 0;
  if (rawFeat && rawFeat.index != null) index = rawFeat.index;
  else if (raw.featured_output_index != null) index = raw.featured_output_index;
  const out = outputs[index] || outputs[0] || {};
  const normalized = normalizeHistoryOutput(out, index);
  if (raw && raw.original_failed != null && !normalized.originalFailed) {
    normalized.originalFailed = _toBool(raw.original_failed, false);
  }
  normalized.index = index;
  return normalized;
}

function _emptyGenerationRecord() {
  return {
    id: "", kind: "generation", status: "running", workflow: "", workflowVersion: "",
    preset: "", prompt: "", negativePrompt: "", startedAt: "", completedAt: "",
    durationMs: null, favorite: false, note: "", tags: [], models: [],
    outputCount: 0, hasImage: false, previewOnly: false, originalAvailable: false,
    featuredOutput: { index: 0, thumbUrl: "", previewUrl: "", originalUrl: "", originalFailed: false },
    runId: "",
  };
}

function _nowIso() {
  try { return new Date().toISOString(); } catch (err) { return ""; }
}

function _emptyGenerationDetail(id) {
  const rec = _emptyGenerationRecord();
  return Object.assign({}, rec, {
    id: id || rec.id,
    runId: id || rec.runId,
    outputs: [],
    attempts: [],
    errors: [{ code: "load_failed", message: "Generation record unavailable", at: _nowIso() }],
    exportState: "none",
    params: {},
    timing: null,
  });
}

function _emptyExperimentDetail(id) {
  return {
    id: id || "", kind: "experiment", name: id || "", status: "running",
    workflow: "", preset: "", prompt: "", startedAt: "", completedAt: "", durationMs: null,
    favorite: false, note: "", tags: [], models: [],
    trueCellCount: 0, resultCount: 0, failedCount: 0, interruptedCount: 0,
    axisLabels: { x: "", y: "" },
    cover: [null, null, null, null],
    cells: [],
    errors: [{ code: "load_failed", message: "Experiment record unavailable", at: _nowIso() }],
  };
}

// ── Bridge implementation (maps contract → current legacy endpoints) ─────
//
// Until the History V2 backend repository lands, the bridge talks to the
// legacy endpoints under {apiBase}:
//   listFeed          → GET  {apiBase}/history
//   getGeneration     → GET  {apiBase}/run-history/{id}
//   setFavorite/Note  → PATCH {apiBase}/run-history/{id}/annotations
// previewOnly / originalAvailable are NOT supported by the legacy endpoint
// and are applied as client-side filters over the returned page items.
// Every fetch error resolves to a safe default — the bridge never throws.

function _createBridgeRepository(apiBase) {
  return {
    getModeInfo: function () { return { mode: "bridge", repository: "bridge" }; },
    listFeed: function (query) { return _bridgeListFeed(apiBase, query); },
    getGeneration: function (id) { return _bridgeGetGeneration(apiBase, id); },
    getExperiment: function (id) { return _bridgeGetExperiment(apiBase, id); },
    setFavorite: function (id, favorite) { return _bridgeSetFavorite(apiBase, id, favorite); },
    setNote: function (id, note) { return _bridgeSetNote(apiBase, id, note); },
    setFeaturedOutput: function () { return _notAvailable(); },
    retryExperiment: function () { return _notAvailable(); },
    retryCell: function () { return _notAvailable(); },
    resumeExperiment: function () { return _notAvailable(); },
    cancelExperiment: function () { return _notAvailable(); },
    generateOriginal: function () { return _notAvailable(); },
    generateOriginalForCell: function () { return _notAvailable(); },
    listFacets: function () { return _bridgeListFacets(apiBase); },
  };
}

function _notAvailable() {
  return Promise.resolve({ accepted: false, message: "History V2 repository method not available" });
}

function _safeFetchJson(url, options) {
  return fetch(url, options || {})
    .then(function (res) {
      if (!res.ok) return null;
      return res.json().catch(function () { return null; });
    })
    .catch(function () { return null; });
}

function _cursorToOffset(cursor) {
  if (typeof cursor === "string" && cursor.indexOf("offset:") === 0) {
    const n = parseInt(cursor.slice(7), 10);
    if (!isNaN(n) && n >= 0) return n;
  }
  return 0;
}

function _mapLegacySort(sort) {
  if (sort === "workflow_az") return "preset_az";
  if (sort === "workflow_za") return "preset_za";
  return sort;
}

function _applyClientSideFilters(items, q) {
  let result = Array.isArray(items) ? items : [];
  if (q.previewOnly) result = result.filter(function (it) { return !!it.previewOnly; });
  if (q.originalAvailable) result = result.filter(function (it) { return !!it.originalAvailable; });
  return result;
}

function _facetsFromItems(items) {
  const workflows = [];
  const presets = [];
  items.forEach(function (it) {
    if (it.workflow && workflows.indexOf(it.workflow) === -1) workflows.push(it.workflow);
    if (it.preset && presets.indexOf(it.preset) === -1) presets.push(it.preset);
  });
  workflows.sort();
  presets.sort();
  return { workflows: workflows, presets: presets };
}

function _bridgeListFeed(apiBase, query) {
  const q = query || {};
  const limit = q.limit != null && q.limit > 0 ? q.limit : 24;
  const offset = _cursorToOffset(q.cursor);
  const page = Math.floor(offset / limit) + 1;

  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(limit));
  if (q.search) params.set("search", q.search);
  // Legacy endpoint is single-kind: only send `kind` when exactly one kind requested.
  if (Array.isArray(q.kinds) && q.kinds.length === 1) params.set("kind", q.kinds[0]);
  if (Array.isArray(q.statuses) && q.statuses.length === 1) params.set("status", q.statuses[0]);
  if (q.favoriteOnly) params.set("favorite_only", "true");
  if (q.preset) params.set("preset", q.preset);
  if (q.dateFrom) params.set("date_from", q.dateFrom);
  if (q.dateTo) params.set("date_to", q.dateTo);
  if (q.hasImage) params.set("has_image", "true");
  if (q.sort) params.set("sort", _mapLegacySort(q.sort));

  const url = apiBase + "/history?" + params.toString();
  return _safeFetchJson(url).then(function (data) {
    const rawItems = data && Array.isArray(data.items) ? data.items : [];
    // previewOnly / originalAvailable are not supported by the legacy
    // endpoint → applied client-side over the returned page items.
    const feedItems = _applyClientSideFilters(rawItems.map(normalizeFeedItem), q);
    const total = data && typeof data.total === "number" ? data.total : rawItems.length;
    const hasMore = data && typeof data.has_more === "boolean"
      ? data.has_more
      : (offset + rawItems.length) < total;
    return {
      items: feedItems,
      nextCursor: hasMore ? "offset:" + (offset + feedItems.length) : null,
      total: total,
      hasMore: hasMore,
      facets: _facetsFromItems(feedItems),
    };
  });
}

function _bridgeGetGeneration(apiBase, id) {
  const url = apiBase + "/run-history/" + encodeURIComponent(id || "");
  return _safeFetchJson(url).then(function (data) {
    if (!data || typeof data !== "object") {
      const fallback = _emptyGenerationDetail(id);
      fallback.errors = [{ code: "load_failed", message: "Run history lookup failed", at: _nowIso() }];
      return fallback;
    }
    const item = normalizeFeedItem(data);
    const rawOutputs = Array.isArray(data.outputs) ? data.outputs : [];
    return Object.assign({}, item, {
      outputs: rawOutputs.map(function (o, i) {
        return normalizeHistoryOutput(o, i);
      }),
      attempts: [],
      errors: [],
      exportState: "none",
      params: {},
      timing: null,
    });
  });
}

function _bridgeGetExperiment(apiBase, id) {
  // Best-effort: look the experiment up through the /history feed.  Cell
  // detail is not available on the legacy endpoint → empty cells.
  return _bridgeListFeed(apiBase, { search: id, limit: 100, kinds: ["experiment"] })
    .then(function (page) {
      let found = null;
      page.items.forEach(function (it) {
        if (it.id === id) found = it;
      });
      if (!found) return _emptyExperimentDetail(id);
      return Object.assign({}, found, { cells: [] });
    });
}

function _bridgeSetFavorite(apiBase, id, favorite) {
  const value = !!favorite;
  const url = apiBase + "/run-history/" + encodeURIComponent(id || "") + "/annotations";
  return _safeFetchJson(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favorite: value }),
  }).then(function (data) {
    return data && typeof data === "object" ? data : { favorite: value };
  });
}

function _bridgeSetNote(apiBase, id, note) {
  const value = note != null ? String(note) : "";
  const url = apiBase + "/run-history/" + encodeURIComponent(id || "") + "/annotations";
  return _safeFetchJson(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: value }),
  }).then(function (data) {
    return data && typeof data === "object" ? data : { note: value };
  });
}

function _bridgeListFacets(apiBase) {
  return _bridgeListFeed(apiBase, { limit: 200 }).then(function (page) {
    return page.facets;
  });
}

// ── History V2 backend implementation (real HTTP, no fixture fallback) ──
//
// Talks to the real History V2 API under {apiBase}/history-v2/*.  Unlike the
// bridge, failures are surfaced truthfully and never resolve to demo data:
//   listFeed           → rejects on HTTP/network failure (UI renders the error)
//   getGeneration      → resolves to a record carrying a "load_failed" error
//   getExperiment      → resolves to a record carrying a "load_failed" error
//   setFavorite/Note   → reject on failure; a 404 on generations retries once
//                        against experiments (the UI calls these for both kinds)
//   setFeaturedOutput  → rejects on failure (server validates ownership)
//   retryCell          → POST the per-cell retry route (D5: the ONLY retry
//                        path; automatic Retry-all is forbidden)
//   retryExperiment    → unavailable placeholder (D5 forbids retry-all)
//   resume/cancel      → POST the modern action routes
//   generateOriginal*  → honest "not available" placeholder (deferred)

function _createV2Repository(apiBase) {
  return {
    getModeInfo: function () { return { mode: "v2", repository: "v2" }; },
    listFeed: function (query) { return _v2ListFeed(apiBase, query); },
    getGeneration: function (id) { return _v2GetGeneration(apiBase, id); },
    getExperiment: function (id) { return _v2GetExperiment(apiBase, id); },
    setFavorite: function (id, favorite) { return _v2SetFavorite(apiBase, id, favorite); },
    setNote: function (id, note) { return _v2SetNote(apiBase, id, note); },
    setFeaturedOutput: function (generationId, outputIndex) {
      return _v2SetFeaturedOutput(apiBase, generationId, outputIndex);
    },
    retryExperiment: function () { return _notAvailable(); },
    retryCell: function (experimentId, cellId) { return _v2RetryCell(apiBase, experimentId, cellId); },
    resumeExperiment: function (experimentId) { return _v2ResumeExperiment(apiBase, experimentId); },
    cancelExperiment: function (experimentId) { return _v2CancelExperiment(apiBase, experimentId); },
    generateOriginal: function () { return _notAvailable(); },
    generateOriginalForCell: function () { return _notAvailable(); },
    listFacets: function () { return _v2ListFacets(apiBase); },
  };
}

// Real HTTP request against the History V2 backend.  Rejects on any failure
// — HTTP errors carry `.httpStatus` so callers can special-case e.g. 404;
// network failures reject with the fetch message.  There is deliberately no
// fixture fallback anywhere in this path.
function _v2FetchJson(url, options) {
  return fetch(url, options || {})
    .then(function (res) {
      if (!res.ok) {
        const err = new Error("History V2 request failed (HTTP " + res.status + ")");
        err.httpStatus = res.status;
        throw err;
      }
      return res.json();
    })
    .catch(function (err) {
      if (err && err.httpStatus) throw err;
      const message = err && err.message ? err.message : "network error";
      throw new Error("History V2 unavailable: " + message);
    });
}

function _v2PatchJson(url, body) {
  return _v2FetchJson(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// Human-readable failure message from a normalized v2 error.
function _v2FailureMessage(err, label) {
  const status = err && err.httpStatus;
  if (status != null) return label + " (HTTP " + status + ")";
  return label + ": " + (err && err.message ? err.message : "network error");
}

function _v2ClientError(err, label) {
  return new Error(_v2FailureMessage(err, label));
}

function _v2LoadFailedDetail(id, kind, message) {
  const fallback = kind === "experiment" ? _emptyExperimentDetail(id) : _emptyGenerationDetail(id);
  fallback.errors = [{ code: "load_failed", message: message, at: _nowIso() }];
  return fallback;
}

function _canonicalFeedOrder(sort) {
  // UI-canonical workflow sort names map to the production V2 feed order
  // contract (history_v2_routes accepts workflow_asc / workflow_desc).
  if (sort === "workflow_az") return "workflow_asc";
  if (sort === "workflow_za") return "workflow_desc";
  return sort;
}

function _v2ListFeed(apiBase, query) {
  const q = query || {};
  const limit = q.limit || 24;
  const params = new URLSearchParams();
  params.set("limit", String(limit));

  // kind: mixed (default), generation, or experiment — derived from q.kinds.
  const kinds = Array.isArray(q.kinds) ? q.kinds : [];
  let kind = "mixed";
  if (kinds.length === 1 && kinds[0] === "generation") kind = "generation";
  else if (kinds.length === 1 && kinds[0] === "experiment") kind = "experiment";
  params.set("kind", kind);

  // Cursor is passed through opaquely — the backend owns pagination state
  // (no "offset:" parsing here; that stays bridge-only).
  if (typeof q.cursor === "string" && q.cursor !== "") params.set("cursor", q.cursor);
  if (q.search) params.set("search", q.search);
  if (q.workflow) params.set("workflow_id", q.workflow);
  if (q.preset) params.set("preset_id", q.preset);
  if (q.favoriteOnly) params.set("favorite", "true");
  if (q.dateFrom) params.set("date_from", q.dateFrom);
  if (q.dateTo) params.set("date_to", q.dateTo);
  if (q.previewOnly) params.set("preview_only", "true");
  if (q.originalAvailable) params.set("has_original", "true");
  if (q.hasImage) params.set("has_image", "true");
  if (q.sort) params.set("order", _canonicalFeedOrder(q.sort)); // "newest"/"oldest"/"fastest"/"slowest" pass through
  if (Array.isArray(q.statuses) && q.statuses.length > 0) {
    // Statuses are canonicalized here so only wire-valid values reach the
    // backend; unknown aliases are dropped rather than sent through.
    const statuses = normalizeStatuses(q.statuses);
    if (statuses.length > 0) params.set("statuses", statuses.join(","));
  }

  const url = apiBase + "/history-v2/feed?" + params.toString();
  return _v2FetchJson(url).then(function (data) {
    const rawItems = data && Array.isArray(data.items) ? data.items : [];
    const items = rawItems.map(normalizeFeedItem);
    const nextCursor = data && data.next_cursor ? data.next_cursor : null;
    return {
      items: items,
      nextCursor: nextCursor,
      total: data && typeof data.total === "number" ? data.total : rawItems.length,
      hasMore: !!(data && data.has_more !== false && nextCursor),
      facets: _facetsFromItems(items),
    };
  });
}

function _v2GetGeneration(apiBase, id) {
  const url = apiBase + "/history-v2/generations/" + encodeURIComponent(id || "");
  return _v2FetchJson(url)
    .then(function (data) {
      const raw = data && data.item && typeof data.item === "object" ? data.item : null;
      if (!raw) {
        return _v2LoadFailedDetail(id, "generation", "History V2 generation lookup failed (no item)");
      }
      const item = normalizeFeedItem(raw);
      const outputs = (Array.isArray(raw.outputs) ? raw.outputs : []).map(normalizeHistoryOutput);
      const attempts = normalizeHistoryAttempts(raw.attempts);
      return Object.assign({}, item, {
        outputs: outputs,
        attempts: attempts,
        errors: Array.isArray(raw.errors) ? raw.errors : [],
        exportState: _firstString(raw.export_state, "none"),
        params: raw.params && typeof raw.params === "object" ? raw.params : {},
        timing: raw.timing && typeof raw.timing === "object" ? raw.timing : null,
      });
    })
    .catch(function (err) {
      return _v2LoadFailedDetail(id, "generation", _v2FailureMessage(err, "History V2 generation lookup failed"));
    });
}

function _v2GetExperiment(apiBase, id) {
  const url = apiBase + "/history-v2/experiments/" + encodeURIComponent(id || "");
  return _v2FetchJson(url)
    .then(function (data) {
      const raw = data && data.item && typeof data.item === "object" ? data.item : null;
      if (!raw) {
        return _v2LoadFailedDetail(id, "experiment", "History V2 experiment lookup failed (no item)");
      }
      const item = normalizeFeedItem(raw);
      const cells = (Array.isArray(raw.cells) ? raw.cells : []).map(function (c, index) {
        const cell = c && typeof c === "object" ? c : {};
        const generation = cell.generation && typeof cell.generation === "object" ? cell.generation : {};
        const rawOutputs = Array.isArray(cell.outputs)
          ? cell.outputs
          : (Array.isArray(generation.outputs) ? generation.outputs : []);
        const outputs = rawOutputs.map(normalizeHistoryOutput);
        const featuredIndex = cell.featured_output_index != null ? cell.featured_output_index : 0;
        const featured = outputs.length > 0
          ? (outputs[featuredIndex] || outputs[0])
          : normalizeHistoryOutput(cell, index);
        const attempts = normalizeHistoryAttempts(
          Array.isArray(cell.attempts) ? cell.attempts : generation.attempts,
        );
        return Object.assign({}, featured, {
          key: _firstString(cell.key, cell.cell_id, cell.cellId),
          cellId: _firstString(cell.cell_id, cell.cellId, cell.key),
          index: cell.index != null ? cell.index : index,
          axis: cell.axis && typeof cell.axis === "object"
            ? { x: _firstString(cell.axis.x), y: _firstString(cell.axis.y) }
            : { x: "", y: "" },
          status: _firstString(cell.status, generation.status),
          outputs: outputs,
          attempts: attempts,
          attemptCount: cell.attempt_count != null ? _toInt(cell.attempt_count, attempts.length) : attempts.length,
          durationMs: _toIntOrNull(cell.duration_ms != null ? cell.duration_ms : cell.durationMs),
          error: cell.error || null,
          favorite: _toBool(cell.favorite, false),
        });
      });
      const cover = (raw.cover || item.cover || []).slice(0, 4);
      return Object.assign({}, item, { cells: cells, cover: cover });
    })
    .catch(function (err) {
      return _v2LoadFailedDetail(id, "experiment", _v2FailureMessage(err, "History V2 experiment lookup failed"));
    });
}

function _v2SetFavorite(apiBase, id, favorite) {
  const value = !!favorite;
  const idEnc = encodeURIComponent(id || "");
  const generationsUrl = apiBase + "/history-v2/generations/" + idEnc + "/favorite";
  const experimentsUrl = apiBase + "/history-v2/experiments/" + idEnc + "/favorite";
  return _v2PatchJson(generationsUrl, { favorite: value })
    .catch(function (err) {
      if (!(err && err.httpStatus === 404)) throw _v2ClientError(err, "History V2 favorite update failed");
      // 404 on generations → the id may be an experiment; retry once.
      return _v2PatchJson(experimentsUrl, { favorite: value })
        .catch(function (err2) {
          throw _v2ClientError(err2, "History V2 favorite update failed");
        });
    })
    .then(function () {
      return { favorite: value };
    });
}

function _v2SetNote(apiBase, id, note) {
  const value = note != null ? String(note) : "";
  const idEnc = encodeURIComponent(id || "");
  const generationsUrl = apiBase + "/history-v2/generations/" + idEnc + "/note";
  const experimentsUrl = apiBase + "/history-v2/experiments/" + idEnc + "/note";
  return _v2PatchJson(generationsUrl, { note: value })
    .catch(function (err) {
      if (!(err && err.httpStatus === 404)) throw _v2ClientError(err, "History V2 note update failed");
      // 404 on generations → the id may be an experiment; retry once.
      return _v2PatchJson(experimentsUrl, { note: value })
        .catch(function (err2) {
          throw _v2ClientError(err2, "History V2 note update failed");
        });
    })
    .then(function () {
      return { note: value };
    });
}

function _v2SetFeaturedOutput(apiBase, generationId, outputIndex) {
  const url = apiBase + "/history-v2/generations/" + encodeURIComponent(generationId || "") + "/featured";
  return _v2PatchJson(url, { output_index: outputIndex })
    .catch(function (err) {
      throw _v2ClientError(err, "History V2 featured output update failed");
    })
    .then(function () {
      return { featuredOutputIndex: outputIndex };
    });
}

function _v2ListFacets(apiBase) {
  return _v2ListFeed(apiBase, { limit: 200 }).then(function (page) {
    return page.facets;
  });
}

// ── Modern experiment actions (D5) ───────────────────────────────────────
//
// Action endpoints live on the frozen History V2 surface
// (/history-v2/experiments/{id}/{cancel,resume} and
// /history-v2/experiments/{id}/cells/{cell_id}/retry).  D5 forbids automatic
// Retry-all: only retryCell(experimentId, cellId) may call the cell retry
// route; the retryExperiment method stays on the interface for parity but is
// unavailable (it must never submit multiple failed cells).  Every action
// resolves to an { accepted, message, ... } shape; HTTP/network failures
// reject truthfully like the rest of the v2 repository.

function _v2ActionJson(url) {
  return _v2FetchJson(url, { method: "POST" });
}

function _v2RetryCell(apiBase, experimentId, cellId) {
  const url = apiBase + "/history-v2/experiments/" + encodeURIComponent(experimentId || "")
    + "/cells/" + encodeURIComponent(cellId || "") + "/retry";
  return _v2ActionJson(url).then(function (data) {
    return { accepted: true, message: "Retry queued", ...(data && typeof data === "object" ? data : {}) };
  });
}

function _v2ResumeExperiment(apiBase, experimentId) {
  const url = apiBase + "/history-v2/experiments/" + encodeURIComponent(experimentId || "") + "/resume";
  return _v2ActionJson(url).then(function (data) {
    return { accepted: true, message: "Resume queued", ...(data && typeof data === "object" ? data : {}) };
  });
}

function _v2CancelExperiment(apiBase, experimentId) {
  const url = apiBase + "/history-v2/experiments/" + encodeURIComponent(experimentId || "") + "/cancel";
  return _v2ActionJson(url).then(function (data) {
    return { accepted: true, message: "Cancel queued", ...(data && typeof data === "object" ? data : {}) };
  });
}
