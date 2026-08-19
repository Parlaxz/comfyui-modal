// Modal Studio — History V2 Fixture Repository
//
// Deterministic in-memory dataset + repository implementation used until the
// real History V2 backend repository lands (or whenever the legacy /history
// endpoint is unreachable).  Deterministic only: no time-of-day clocks and
// no random number generation anywhere — every value is derived from a fixed
// base timestamp and per-record constants, so tests and UI screenshots are
// reproducible.
//
// Single source of truth for experiment covers: cover is always derived from
// cells — cover = cells.slice(0, 4) mapped to { thumbUrl, cellKey }, then
// padded with null to exactly 4 slots (null = empty block).

import { normalizeFeedItem } from "./history-v2-repository.js";

// ── Fixed clock ──────────────────────────────────────────────────────────

export const BASE_TIMESTAMP = "2026-08-10T12:00:00.000Z";
const BASE_EPOCH = Date.parse(BASE_TIMESTAMP);

function _isoAt(offsetMs) {
  return new Date(BASE_EPOCH - offsetMs).toISOString();
}

// ── Deterministic helpers ────────────────────────────────────────────────

function _stableHash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/**
 * Build a deterministic SVG thumbnail data URI for a (seed, index) pair.
 * Color is derived from a stable hash of seed+index; the label is short.
 * @param {string} seed
 * @param {number} index
 * @returns {string} data:image/svg+xml;utf8,... URI
 */
export function makeSvgThumbUri(seed, index) {
  const key = String(seed) + ":" + (index == null ? 0 : index);
  const hue = _stableHash(key) % 360;
  const label = "out " + index;
  const svg = "<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256'>"
    + "<rect width='256' height='256' fill='hsl(" + hue + ",68%,42%)'/>"
    + "<text x='128' y='136' font-family='sans-serif' font-size='26' fill='#ffffff' text-anchor='middle'>"
    + label + "</text></svg>";
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

// ── Dataset: 28 generations ──────────────────────────────────────────────
// 14 success / 4 interrupted / 4 failed / 4 canceled / 2 running.
// ≥4 workflows, ≥3 presets, ≥3 models, several tags, favorites, one note.
// Durations 800ms–90s (gen_008 fastest, gen_012 slowest).
// gen_003 (4 outputs), gen_007 (2), gen_012 (5).
// gen_005 preview OK but original FAILED (originalFailed, originalAvailable).
// gen_014 no image (outputCount 0). gen_018 + gen_022 preview-only.
// gen_028 is the running generation that already has an image.

function _gen(id, status, workflow, preset, model, durationMs, offsetSec, outputCount, opts) {
  const o = opts || {};
  return {
    id: id,
    status: status,
    workflow: workflow,
    preset: preset,
    model: model,
    durationMs: durationMs,
    offsetSec: offsetSec,
    outputCount: outputCount,
    favorite: !!o.favorite,
    note: o.note || "",
    tags: o.tags || [],
    previewOnly: !!o.previewOnly,
    originalAvailable: o.originalAvailable != null ? o.originalAvailable : (outputCount > 0 && !o.previewOnly),
    originalFailed: !!o.originalFailed,
    hasImage: o.hasImage != null ? o.hasImage : outputCount > 0,
  };
}

const GENERATION_SPECS = [
  _gen("gen_001", "success", "Portrait Pro", "preset_a", "sd_xl_base", 4200, 690, 1, { tags: ["portrait"] }),
  _gen("gen_002", "success", "Portrait Pro", "preset_a", "sd_xl_base", 8600, 780, 1, { favorite: true, tags: ["portrait"] }),
  _gen("gen_003", "success", "Portrait Pro", "preset_a", "flux_dev", 15300, 870, 4, { tags: ["portrait", "multi"] }),
  _gen("gen_004", "success", "Portrait Pro", "preset_a", "dreamshaper_xl", 2900, 960, 1, { tags: ["portrait"] }),
  _gen("gen_005", "success", "Portrait Pro", "preset_a", "sd_xl_base", 12400, 1050, 1, { originalFailed: true, originalAvailable: true, tags: ["portrait"] }),
  _gen("gen_006", "success", "Portrait Pro", "preset_a", "flux_dev", 6100, 1140, 1, { tags: ["portrait"] }),
  _gen("gen_007", "success", "Portrait Pro", "preset_a", "dreamshaper_xl", 9800, 1230, 2, { tags: ["portrait", "multi"] }),
  _gen("gen_008", "success", "Portrait Pro", "preset_a", "sd_xl_base", 800, 1320, 1, { tags: ["fast"] }),
  _gen("gen_009", "success", "Landscape Ultra", "preset_a", "flux_dev", 13700, 1410, 1, { favorite: true, note: "Client approved variant B", tags: ["landscape", "client"] }),
  _gen("gen_010", "success", "Landscape Ultra", "preset_a", "dreamshaper_xl", 5100, 1500, 1, { tags: ["landscape"] }),
  _gen("gen_011", "success", "Landscape Ultra", "preset_b", "sd_xl_base", 17200, 1590, 1, { tags: ["landscape"] }),
  _gen("gen_012", "success", "Landscape Ultra", "preset_b", "flux_dev", 90000, 1680, 5, { tags: ["landscape", "batch"] }),
  _gen("gen_013", "success", "Landscape Ultra", "preset_b", "dreamshaper_xl", 3400, 1770, 1, { tags: ["landscape"] }),
  _gen("gen_014", "success", "Landscape Ultra", "preset_b", "sd_xl_base", 4800, 1860, 0, { hasImage: false }),
  _gen("gen_015", "interrupted", "Concept Lab", "preset_b", "flux_dev", 2200, 1950, 1, { tags: ["concept"] }),
  _gen("gen_016", "interrupted", "Concept Lab", "preset_b", "dreamshaper_xl", 4100, 2040, 1, { tags: ["concept"] }),
  _gen("gen_017", "interrupted", "Concept Lab", "preset_b", "sd_xl_base", 6700, 2130, 1, { tags: ["concept"] }),
  _gen("gen_018", "interrupted", "Concept Lab", "preset_b", "flux_dev", 3800, 2220, 1, { previewOnly: true, originalAvailable: false, tags: ["concept", "preview"] }),
  _gen("gen_019", "failed", "Concept Lab", "preset_b", "dreamshaper_xl", 2500, 2310, 1, { tags: ["concept"] }),
  _gen("gen_020", "failed", "Concept Lab", "preset_b", "sd_xl_base", 3100, 2400, 1, { tags: ["concept"] }),
  _gen("gen_021", "failed", "Clean Workflow", "preset_c", "flux_dev", 5400, 2490, 1, { tags: ["clean"] }),
  _gen("gen_022", "failed", "Clean Workflow", "preset_c", "dreamshaper_xl", 1900, 2580, 1, { previewOnly: true, originalAvailable: false, tags: ["clean", "preview"] }),
  _gen("gen_023", "canceled", "Clean Workflow", "preset_c", "sd_xl_base", 1200, 2670, 1, { tags: ["clean"] }),
  _gen("gen_024", "canceled", "Clean Workflow", "preset_c", "flux_dev", 2300, 2760, 1, { tags: ["clean"] }),
  _gen("gen_025", "canceled", "Clean Workflow", "preset_c", "dreamshaper_xl", 3600, 2850, 1, { tags: ["clean"] }),
  _gen("gen_026", "canceled", "Clean Workflow", "preset_c", "sd_xl_base", 4700, 2940, 1, { tags: ["clean"] }),
  _gen("gen_027", "running", "Clean Workflow", "preset_c", "flux_dev", null, 120, 0, { hasImage: false, tags: ["clean"] }),
  _gen("gen_028", "running", "Clean Workflow", "preset_c", "dreamshaper_xl", 6200, 45, 1, { hasImage: true, tags: ["clean", "running"] }),
];

const PROMPT_POOL = {
  "Portrait Pro": [
    "Portrait of Ada in soft window light",
    "Portrait of Ken in dramatic rim light",
    "Portrait of Mara with a floral crown",
  ],
  "Landscape Ultra": [
    "Wide shot of a misty alpine valley at dawn",
    "Sunrise over rugged coastal cliffs",
    "Golden hour across rolling desert dunes",
  ],
  "Concept Lab": [
    "Concept art of a clockwork dragon",
    "Concept art of a floating market city",
    "Concept art of an orbital greenhouse",
  ],
  "Clean Workflow": [
    "Clean render of a chrome teapot",
    "Clean render of a glass sphere on a pedestal",
    "Clean render of a paper lantern",
  ],
};

function _promptFor(workflow, id) {
  const pool = PROMPT_POOL[workflow];
  if (!pool || pool.length === 0) return "Studio generation";
  return pool[_stableHash(id) % pool.length];
}

function _buildGenerationRecord(spec) {
  const outputCount = spec.outputCount || 0;
  const isRunning = spec.status === "running";
  const startedAt = _isoAt(spec.offsetSec * 1000);
  const completedAt = isRunning ? "" : _isoAt(Math.max(0, spec.offsetSec * 1000 - spec.durationMs));
  const durationMs = isRunning && spec.durationMs == null ? null : spec.durationMs;
  const outputs = [];
  for (let i = 0; i < outputCount; i++) {
    const originalFailed = spec.originalFailed && i === 0;
    const hasOriginal = !spec.previewOnly && !originalFailed;
    outputs.push({
      index: i,
      thumbUrl: makeSvgThumbUri(spec.id, i),
      previewUrl: makeSvgThumbUri(spec.id, i),
      originalUrl: hasOriginal ? makeSvgThumbUri(spec.id + "_orig", i) : "",
      originalFailed: originalFailed,
      status: "success",
    });
  }
  return {
    id: spec.id,
    kind: "generation",
    status: spec.status,
    workflow: spec.workflow,
    workflow_version: "v3",
    preset: spec.preset,
    prompt: _promptFor(spec.workflow, spec.id),
    negative_prompt: "blurry, low quality, oversaturated",
    started_at: startedAt,
    completed_at: completedAt,
    duration_ms: durationMs,
    favorite: spec.favorite,
    note: spec.note,
    tags: spec.tags.slice(),
    models: [spec.model],
    outputs: outputs,
    has_image: spec.hasImage,
    preview_only: spec.previewOnly,
    original_available: spec.originalAvailable,
    run_id: "run_" + spec.id,
    featured_output_index: 0,
  };
}

// ── Dataset: 7 experiments ───────────────────────────────────────────────
// exp_001 12 cells ALL success (cover 4 filled + 8 not shown).
// exp_002 1 cell success (cover 1 filled + 3 null).
// exp_003 2 cells success (cover 2 filled + 2 null).
// exp_004 3 cells success (cover 3 filled + 1 null).
// exp_005 8 cells: 5 success / 3 failed → status partial.
// exp_006 4 cells all failed → status failed.
// exp_007 6 cells: 2 success / 4 interrupted → status interrupted.
// Cells have stable keys cell_0..cell_N.

function _exp(id, name, workflow, preset, model, status, cellCount, successCount, failedCount, interruptedCount, offsetSec, durationMs, axis, opts) {
  const o = opts || {};
  return {
    id: id,
    name: name,
    workflow: workflow,
    preset: preset,
    model: model,
    status: status,
    cellCount: cellCount,
    successCount: successCount,
    failedCount: failedCount,
    interruptedCount: interruptedCount,
    offsetSec: offsetSec,
    durationMs: durationMs,
    axis: axis || { x: "", y: "" },
    baseCellMs: o.baseCellMs || 800,
    favorite: !!o.favorite,
    note: o.note || "",
    tags: o.tags || [],
  };
}

const EXPERIMENT_SPECS = [
  _exp("exp_001", "Seed sweep \u00b7 Steps", "Portrait Pro", "preset_a", "sd_xl_base", "success", 12, 12, 0, 0, 3200, 64000,
    { x: "Seed", y: "Steps", xValue: function (i) { return i; }, yValue: function () { return 20; } },
    { tags: ["sweep"] }),
  _exp("exp_002", "Lora strength A/B", "Portrait Pro", "preset_a", "flux_dev", "success", 1, 1, 0, 0, 3300, 2100,
    { x: "LoRA", y: "" }, { tags: ["lora"] }),
  _exp("exp_003", "Checkpoint comparison", "Landscape Ultra", "preset_b", "dreamshaper_xl", "success", 2, 2, 0, 0, 3400, 4200,
    { x: "", y: "" }, { tags: ["checkpoint"] }),
  _exp("exp_004", "Scheduler sweep", "Concept Lab", "preset_b", "sd_xl_base", "success", 3, 3, 0, 0, 3500, 9800,
    { x: "Scheduler", y: "" }, { tags: ["scheduler"] }),
  _exp("exp_005", "Upscale variant matrix", "Landscape Ultra", "preset_b", "flux_dev", "partial", 8, 5, 3, 0, 3600, 31000,
    { x: "Upscale", y: "Model" }, { tags: ["upscale"] }),
  _exp("exp_006", "Broken prompt batch", "Concept Lab", "preset_c", "sd_xl_base", "failed", 4, 0, 4, 0, 3700, 15400,
    { x: "", y: "" }, { tags: ["failed"] }),
  _exp("exp_007", "Denoise ramp", "Clean Workflow", "preset_c", "flux_dev", "interrupted", 6, 2, 0, 4, 3800, 22000,
    { x: "Denoise", y: "" }, { tags: ["denoise"] }),
];

function _cellStatus(spec, i) {
  if (i < spec.successCount) return "success";
  if (spec.failedCount > 0 && i < spec.successCount + spec.failedCount) return "failed";
  if (spec.interruptedCount > 0 && i < spec.successCount + spec.failedCount + spec.interruptedCount) return "interrupted";
  return "success";
}

function _buildExperimentRecord(spec) {
  const cells = [];
  const startedAt = _isoAt(spec.offsetSec * 1000);
  const completedAt = _isoAt(Math.max(0, spec.offsetSec * 1000 - spec.durationMs));
  for (let i = 0; i < spec.cellCount; i++) {
    const status = _cellStatus(spec, i);
    const hasImage = status === "success";
    let axisX = "";
    let axisY = "";
    if (spec.axis.x) axisX = spec.axis.xValue != null ? String(spec.axis.xValue(i)) : String(i);
    if (spec.axis.y) axisY = spec.axis.yValue != null ? String(spec.axis.yValue(i)) : spec.axis.y;
    cells.push({
      key: "cell_" + i,
      index: i,
      axis: { x: axisX, y: axisY },
      status: status,
      thumbUrl: hasImage ? makeSvgThumbUri(spec.id, i) : "",
      previewUrl: hasImage ? makeSvgThumbUri(spec.id, i) : "",
      originalUrl: hasImage ? makeSvgThumbUri(spec.id + "_orig", i) : "",
      originalFailed: false,
      durationMs: hasImage ? spec.baseCellMs + i * 137 : null,
      error: status === "failed" ? "Sample generation failed" : (status === "interrupted" ? "Stopped mid-sample" : ""),
      favorite: false,
    });
  }
  return {
    id: spec.id,
    kind: "experiment",
    name: spec.name,
    status: spec.status,
    workflow: spec.workflow,
    preset: spec.preset,
    prompt: _promptFor(spec.workflow, spec.id),
    started_at: startedAt,
    completed_at: completedAt,
    duration_ms: spec.durationMs,
    favorite: spec.favorite,
    note: spec.note,
    tags: spec.tags.slice(),
    models: [spec.model],
    true_cell_count: spec.cellCount,
    result_count: spec.successCount,
    failed_count: spec.failedCount,
    interrupted_count: spec.interruptedCount,
    axis_labels: { x: spec.axis.x, y: spec.axis.y },
    cells: cells,
  };
}

// ── Dataset builder (exported for tests) ─────────────────────────────────

export function buildFixtureDataset() {
  return {
    generations: GENERATION_SPECS.map(_buildGenerationRecord),
    experiments: EXPERIMENT_SPECS.map(_buildExperimentRecord),
  };
}

// ── Cover helper (single source of truth: cells) ────────────────────────

function _buildExperimentCover(cells) {
  const cover = (cells || []).slice(0, 4).map(function (c) {
    return { thumbUrl: c ? (c.thumbUrl || "") : "", cellKey: c ? (c.key || "") : "" };
  });
  while (cover.length < 4) cover.push(null);
  return cover;
}

// ── Fixture repository ───────────────────────────────────────────────────

export function createFixtureRepository() {
  const dataset = buildFixtureDataset();
  const generations = dataset.generations;
  const experiments = dataset.experiments;

  function feedItems() {
    const items = [];
    generations.forEach(function (g) { items.push(normalizeFeedItem(g)); });
    experiments.forEach(function (e) {
      const item = normalizeFeedItem(e);
      item.cover = _buildExperimentCover(e.cells);
      items.push(item);
    });
    return items;
  }

  function findRaw(id) {
    for (let i = 0; i < generations.length; i++) {
      if (generations[i].id === id) return generations[i];
    }
    for (let j = 0; j < experiments.length; j++) {
      if (experiments[j].id === id) return experiments[j];
    }
    return null;
  }

  function matchesQuery(item, q) {
    if (Array.isArray(q.kinds) && q.kinds.length > 0 && q.kinds.indexOf(item.kind) === -1) return false;
    if (Array.isArray(q.statuses) && q.statuses.length > 0 && q.statuses.indexOf(item.status) === -1) return false;
    if (q.workflow && item.workflow !== q.workflow) return false;
    if (q.preset && item.preset !== q.preset) return false;
    if (q.favoriteOnly && !item.favorite) return false;
    if (q.previewOnly && !item.previewOnly) return false;
    if (q.originalAvailable && !item.originalAvailable) return false;
    if (q.hasImage && !item.hasImage) return false;
    if (q.dateFrom && item.startedAt < q.dateFrom) return false;
    if (q.dateTo && item.startedAt > q.dateTo) return false;
    if (q.search && !_searchMatch(item, q.search)) return false;
    return true;
  }

  function _searchMatch(item, search) {
    const needle = String(search).toLowerCase();
    const haystacks = [item.prompt, item.workflow, item.preset, item.note, item.name, item.id, item.runId]
      .concat(item.tags || [])
      .concat(item.models || []);
    for (let i = 0; i < haystacks.length; i++) {
      if (haystacks[i] && String(haystacks[i]).toLowerCase().indexOf(needle) !== -1) return true;
    }
    return false;
  }

  function _cmpStr(a, b) {
    const x = a || "";
    const y = b || "";
    if (x < y) return -1;
    if (x > y) return 1;
    return 0;
  }

  function _cmpDuration(a, b) {
    if (a == null && b == null) return 0;
    if (a == null) return 1; // nulls last
    if (b == null) return -1;
    return a - b;
  }

  function compareItems(a, b, sort) {
    switch (sort) {
      case "oldest": return _cmpStr(a.startedAt, b.startedAt);
      case "fastest": return _cmpDuration(a.durationMs, b.durationMs);
      case "slowest": return _cmpDuration(b.durationMs, a.durationMs);
      case "workflow_asc": return _cmpStr(a.workflow, b.workflow);
      case "workflow_desc": return _cmpStr(b.workflow, a.workflow);
      case "newest":
      default: return _cmpStr(b.startedAt, a.startedAt);
    }
  }

  function _offsetFromCursor(cursor) {
    if (typeof cursor === "string" && cursor.indexOf("offset:") === 0) {
      const n = parseInt(cursor.slice(7), 10);
      if (!isNaN(n) && n >= 0) return n;
    }
    return 0;
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

  function listFeed(query) {
    const q = query || {};
    const limit = q.limit != null && q.limit > 0 ? q.limit : 24;
    const offset = _offsetFromCursor(q.cursor);
    const items = feedItems().filter(function (item) { return matchesQuery(item, q); });
    const total = items.length;
    items.sort(function (a, b) { return compareItems(a, b, q.sort || "newest"); });
    const page = items.slice(offset, offset + limit);
    const hasMore = offset + page.length < total;
    return Promise.resolve({
      items: page,
      nextCursor: hasMore ? "offset:" + (offset + page.length) : null,
      total: total,
      hasMore: hasMore,
      facets: _facetsFromItems(items),
    });
  }

  function _fixtureTiming(raw) {
    const d = raw.duration_ms;
    if (d == null) return null;
    const samplingMs = Math.round(d * 0.6);
    const clipEncodeMs = Math.round(d * 0.05);
    const vaeDecodeMs = Math.round(d * 0.08);
    const modelLoadMs = Math.round(d * 0.15);
    return {
      endToEndMs: d,
      samplingMs: samplingMs,
      clipEncodeMs: clipEncodeMs,
      vaeDecodeMs: vaeDecodeMs,
      modelLoadMs: modelLoadMs,
      stages: [
        { label: "End-to-End Total", durationMs: d },
        { label: "Model / CLIP Load", durationMs: modelLoadMs },
        { label: "Prompt Encoding", durationMs: clipEncodeMs },
        { label: "Sampling", durationMs: samplingMs },
        { label: "VAE Decode", durationMs: vaeDecodeMs },
      ],
    };
  }

  function getGeneration(id) {
    let raw = null;
    for (let i = 0; i < generations.length; i++) {
      if (generations[i].id === id) { raw = generations[i]; break; }
    }
    if (!raw) {
      return Promise.resolve({
        id: id || "", kind: "generation", status: "running", workflow: "", workflowVersion: "",
        preset: "", prompt: "", negativePrompt: "", startedAt: "", completedAt: "",
        durationMs: null, favorite: false, note: "", tags: [], models: [],
        outputCount: 0, hasImage: false, previewOnly: false, originalAvailable: false,
        featuredOutput: { index: 0, thumbUrl: "", previewUrl: "", originalUrl: "", originalFailed: false },
        runId: id || "",
        outputs: [], attempts: [],
        errors: [{ code: "not_found", message: "Generation not found in fixture dataset", at: _isoAt(0) }],
        exportState: "none", params: {}, timing: null,
      });
    }
    const item = normalizeFeedItem(raw);
    const outputs = (raw.outputs || []).map(function (o, i) {
      return {
        index: o.index != null ? o.index : i,
        thumbUrl: o.thumbUrl || "",
        previewUrl: o.previewUrl || "",
        originalUrl: o.originalUrl || "",
        originalFailed: !!o.originalFailed,
        status: o.status || "success",
      };
    });
    return Promise.resolve(Object.assign({}, item, {
      outputs: outputs,
      attempts: [],
      errors: [],
      exportState: "none",
      params: {
        seed: 42,
        steps: 28,
        cfg: 7,
        sampler: "euler",
        scheduler: "normal",
        denoise: 1,
        width: 1024,
        height: 1024,
      },
      timing: _fixtureTiming(raw),
    }));
  }

  function getExperiment(id) {
    let raw = null;
    for (let i = 0; i < experiments.length; i++) {
      if (experiments[i].id === id) { raw = experiments[i]; break; }
    }
    if (!raw) {
      return Promise.resolve({
        id: id || "", kind: "experiment", name: id || "", status: "running",
        workflow: "", preset: "", prompt: "", startedAt: "", completedAt: "", durationMs: null,
        favorite: false, note: "", tags: [], models: [],
        trueCellCount: 0, resultCount: 0, failedCount: 0, interruptedCount: 0,
        axisLabels: { x: "", y: "" },
        cover: [null, null, null, null],
        cells: [],
        errors: [{ code: "not_found", message: "Experiment not found in fixture dataset", at: _isoAt(0) }],
      });
    }
    const item = normalizeFeedItem(raw);
    item.cover = _buildExperimentCover(raw.cells);
    const cells = (raw.cells || []).map(function (c, i) {
      return {
        key: c.key || "cell_" + i,
        index: c.index != null ? c.index : i,
        axis: c.axis || { x: "", y: "" },
        status: c.status || "success",
        thumbUrl: c.thumbUrl || "",
        previewUrl: c.previewUrl || "",
        originalUrl: c.originalUrl || "",
        originalFailed: !!c.originalFailed,
        durationMs: c.durationMs != null ? c.durationMs : null,
        error: c.error || "",
        favorite: !!c.favorite,
      };
    });
    return Promise.resolve(Object.assign({}, item, { cells: cells }));
  }

  function setFavorite(id, favorite) {
    const value = !!favorite;
    const raw = findRaw(id);
    if (raw) raw.favorite = value;
    return Promise.resolve({ favorite: value });
  }

  function setNote(id, note) {
    const value = note != null ? String(note) : "";
    const raw = findRaw(id);
    if (raw) raw.note = value;
    return Promise.resolve({ note: value });
  }

  function setFeaturedOutput(generationId, outputIndex) {
    let raw = null;
    for (let i = 0; i < generations.length; i++) {
      if (generations[i].id === generationId) { raw = generations[i]; break; }
    }
    const index = outputIndex != null ? outputIndex : 0;
    if (raw) raw.featured_output_index = index;
    return Promise.resolve({ featuredOutputIndex: index });
  }

  function retryExperiment(experimentId) {
    return Promise.resolve({ accepted: true, message: "Fixture: retry queued for " + experimentId });
  }

  function generateOriginal(generationId, outputIndex) {
    return Promise.resolve({
      accepted: true,
      message: "Fixture: original generation queued for " + generationId + " output " + outputIndex,
    });
  }

  function generateOriginalForCell(experimentId, cellKey) {
    return Promise.resolve({
      accepted: true,
      message: "Fixture: cell original generation queued for " + experimentId + " cell " + cellKey,
    });
  }

  function listFacets() {
    return Promise.resolve(_facetsFromItems(feedItems()));
  }

  return {
    getModeInfo: function () { return { mode: "fixture", repository: "fixture" }; },
    listFeed: listFeed,
    getGeneration: getGeneration,
    getExperiment: getExperiment,
    setFavorite: setFavorite,
    setNote: setNote,
    setFeaturedOutput: setFeaturedOutput,
    retryExperiment: retryExperiment,
    generateOriginal: generateOriginal,
    generateOriginalForCell: generateOriginalForCell,
    listFacets: listFacets,
  };
}
