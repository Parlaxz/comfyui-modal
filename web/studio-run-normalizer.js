// Modal Studio — Run Normalizer
//
// Shared helper for resolving image URLs from run-history entries, plus
// timing/annotation normalization consumed by BOTH Playground and History.
// Callers: studio-history.js, studio-playground.js, and any other
// module that needs to display run output images or metadata.
//
// Image URL resolution order (per the spec):
//   1. extra.primary_asset_id  → /assets/<id>
//   2. run.asset_id            → /assets/<id>
//   3. run.output_path         → /studio/outputs/<path>
//
// Returns null when no image source exists on the run.

// ── Nullish-safe helpers ─────────────────────────────────────────────────
//
// These preserve zero/0.0/false values that truthiness checks would hide.
// Use nilTo(x, fallback) to replace null/undefined only, or nilZero(x) to
// treat null/undefined as 0 for numeric fields.

/**
 * Return the value if not null/undefined, otherwise the fallback.
 * Unlike `||`, this preserves 0, 0.0, "", and false.
 * @param {*} value
 * @param {*} fallback
 * @returns {*}
 */
export function nilTo(value, fallback) {
  return value != null ? value : fallback;
}

/**
 * Return the value if not null/undefined, otherwise 0.
 * @param {*} value
 * @returns {*}
 */
export function nilZero(value) {
  return value != null ? value : 0;
}

/**
 * Return the value if not null/undefined and not empty string, otherwise fallback.
 * @param {*} value
 * @param {*} fallback
 * @returns {*}
 */
export function nilOrEmptyTo(value, fallback) {
  if (value == null) return fallback;
  if (typeof value === "string" && value === "") return fallback;
  return value;
}

// ── Timing normalization helpers ─────────────────────────────────────────
//
// Given a raw timings object (or trace, remote_timings, wall_clock_trace,
// scheduler_trace) from the backend, produce readable stage breakdowns
// suitable for display in history and playground.
//
// Stage mapping (deduplicated, no progress-derived values):
//
//   End-to-End Total               end_to_end_total_ms, modal_to_browser
//   Queue / Local Preparation      queue_ms, t0_to_t1
//   Modal Cold Start / Restore     restore_total_ms (from remote_timings or flat)
//   Validation                     workflow_validation_ms, t3_to_t3b
//   Model / CLIP Load              model_load_ms + clip_load_ms (combined),
//                                    clip_load (legacy combined field)
//   Prompt Encoding                clip_encode_ms, clip_encode
//   Sampling                       sampling_ms, sampler
//   VAE Decode                     vae_decode_ms, vae_decode
//   Image / Output I/O             image_io_ms + output_transfer_ms (combined),
//                                    image_io (legacy)
//   Remote Inference Total         remote_inference_total_ms, inference_total
//   Local Materialization          history_finalization_ms
//   Scheduler Execution            scheduler_execution_ms, generation_ms (legacy)
//
// 'generation_ms' maps to the same concept as scheduler_execution_ms but
// is labelled "Legacy scheduler wall time". If scheduler_execution_ms is
// also present, generation_ms is skipped to avoid duplication.
//
// No progress-derived values (overall_percent, completed_nodes, etc.) are
// ever used as timing stages.

function _timingTraceStages(timings) {
  if (!timings || typeof timings !== "object") return {};
  var trace = timings.trace && typeof timings.trace === "object" ? timings.trace : {};
  var wallClock = timings.wall_clock_trace && typeof timings.wall_clock_trace === "object"
    ? timings.wall_clock_trace
    : {};
  return Object.assign(
    {},
    wallClock.stages_unix_s && typeof wallClock.stages_unix_s === "object"
      ? wallClock.stages_unix_s
      : {},
    trace.stages && typeof trace.stages === "object" ? trace.stages : {},
    timings
  );
}

function _timingTraceDerived(timings) {
  if (!timings || typeof timings !== "object") return {};
  var trace = timings.trace && typeof timings.trace === "object" ? timings.trace : {};
  var wallClock = timings.wall_clock_trace && typeof timings.wall_clock_trace === "object"
    ? timings.wall_clock_trace
    : {};
  return Object.assign(
    {},
    wallClock.post_sampler_summary && typeof wallClock.post_sampler_summary === "object"
      ? wallClock.post_sampler_summary
      : {},
    trace.deltas_ms && typeof trace.deltas_ms === "object" ? trace.deltas_ms : {},
    trace.derived_ms && typeof trace.derived_ms === "object" ? trace.derived_ms : {},
    timings.derived_ms && typeof timings.derived_ms === "object" ? timings.derived_ms : {}
  );
}

function _deriveTraceEndToEndMs(timings) {
  var stages = _timingTraceStages(timings);
  var start = stages.browser_run_click;
  if (start == null) start = stages.t0_client_press;
  var end = stages.output_materialized;
  if (end == null) end = stages.t10_local_materialized;
  if (typeof start !== "number" || typeof end !== "number") return null;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return Math.round((end - start) * 1000 * 100) / 100;
}

/**
 * Normalize raw timings into readable stages.
 *
 * Reads from flat canonical fields, legacy deltas_ms/trace format,
 * remote_timings, wall_clock_trace, and scheduler_trace.
 * Prefers canonical fields. Deduplicates equal concepts.
 *
 * @param {object} timings - Raw timings/trace object.
 * @returns {Array<{label:string, durationMs:number, source:string}>}
 */
export function normalizeTimingStages(timings) {
  if (!timings || typeof timings !== "object") return [];
  const stages = [];

  // Resolve the best available timing payload.
  // Order: flat canonical fields > deltas_ms > remote_timings.
  const d = timings.deltas_ms || timings;
  var traceDerived = _timingTraceDerived(timings);

  // ── Helpers ─────────────────────────────────────────────────────────
  /**
   * Add a stage if value is a positive number.
   * Skips duplicates by label — first registration wins (highest priority).
   */
  function addStage(label, value, source) {
    if (value == null || typeof value !== "number" || value <= 0) return;
    if (stages.some(function (s) { return s.label === label; })) return;
    stages.push({ label: label, durationMs: value, source: source || "unknown" });
  }

  /**
   * Resolve first non-null numeric value from field names.
   * Checks flat timings, deltas_ms, and remote_timings.
   */
  function firstValue() {
    var fields = Array.prototype.slice.call(arguments);
    for (var i = 0; i < fields.length; i++) {
      var f = fields[i];
      var v = d[f] != null ? d[f] : timings[f];
      // Also check remote_timings for restore data
      if (v == null && timings.remote_timings && timings.remote_timings[f] != null) {
        v = timings.remote_timings[f];
      }
      if (v == null && traceDerived[f] != null) {
        v = traceDerived[f];
      }
      if (v != null && typeof v === "number") return { value: v, source: f };
    }
    return null;
  }

  // ── Canonical stage order (non-additive hierarchy) ─────────────────
  //
  // Parent stages (End-to-End Total, Remote Invocation Setup, Request
  // Execution, Scheduler Execution) are NOT summed with their children;
  // they represent overlapping intervals.  The UI must display them as
  // parent-level entries that encompass but do not add to the total.
  //
  // Remote Inference Total is rendered ONLY when no individual model
  // child timings exist; otherwise the child stages (Model Load, Prompt
  // Encoding, Sampling, VAE Decode, Image I/O) are shown individually
  // and the overlapping parent is suppressed.

  // 1. End-to-End Total. Older records may only have the authoritative
  // client/materialization markers in trace.stages.
  var e2e = firstValue("end_to_end_total_ms", "modal_to_browser");
  if (!e2e) {
    var traceE2e = _deriveTraceEndToEndMs(timings);
    if (traceE2e != null) {
      e2e = { value: traceE2e, source: "trace:browser_run_click->output_materialized" };
    }
  }
  if (e2e) addStage("End-to-End Total", e2e.value, e2e.source);

  // 2. Local Preparation (from studio_queue / local markers)
  var queue = firstValue("studio_queue_ms", "queue_ms", "t0_to_t1");
  if (queue) addStage("Local Preparation", queue.value, queue.source);

  // 3. Remote Invocation Setup (handle lookup + generator creation)
  // Derived from trace markers when present.
  var _hl_end = firstValue("modal_handle_lookup_completed");
  var _hl_start = firstValue("modal_handle_lookup_started");
  var _gc_end = firstValue("remote_generator_create_completed");
  var _gc_start = firstValue("remote_generator_create_started");
  var _setup_ms = null;
  var _setup_src = null;
  if (_hl_start && _hl_end) {
    _setup_ms = _hl_end.value - _hl_start.value;
    _setup_src = "modal_handle_lookup";
  }
  if (_gc_start && _gc_end) {
    var _gc_delta = _gc_end.value - _gc_start.value;
    if (_gc_delta > 0) {
      _setup_ms = _setup_ms != null ? _setup_ms + _gc_delta : _gc_delta;
      _setup_src = _setup_src ? _setup_src + "+remote_generator_create" : "remote_generator_create";
    }
  }
  if (_setup_ms != null && _setup_ms > 0) {
    addStage("Remote Invocation Setup", Math.round(_setup_ms), _setup_src);
  }

  // 4. Platform Pre-Restore (inferred, cross-process)
  var ppr = firstValue("platform_pre_restore_ms");
  if (ppr) addStage("Platform Pre-Restore (inferred)", ppr.value, ppr.source);

  // 5. Snapshot / Runtime Restore
  var restore = firstValue("restore_total_ms");
  if (restore) addStage("Snapshot / Runtime Restore", restore.value, restore.source);

  // 6. Request Execution (parent, non-additive) — only if no child
  //    model timings exist.  If individual deltas like sampler,
  //    clip_encode, etc. are available, show children instead.
  var _hasChildren = (
    firstValue("clip_load_ms", "clip_load") ||
    firstValue("clip_encode_ms", "clip_encode") ||
    firstValue("sampling_ms", "sampler") ||
    firstValue("vae_decode_ms", "vae_decode") ||
    firstValue("image_io_ms", "image_io")
  );
  if (!_hasChildren) {
    var reqExec = firstValue("remote_inference_total_ms", "inference_total");
    if (reqExec) addStage("Request Execution", reqExec.value, reqExec.source);
  }

  // 7. Model / CLIP Load (child)
  var modelMs = d.model_load_ms != null ? d.model_load_ms : timings.model_load_ms;
  if (modelMs != null) {
    if (modelMs > 0) addStage("Model / CLIP Load", modelMs, "model_load_ms");
  } else {
    var unetMs = d.unet_load_ms != null ? d.unet_load_ms : timings.unet_load_ms;
    var vaeMs = d.vae_load_ms != null ? d.vae_load_ms : timings.vae_load_ms;
    var clipMs = d.clip_load_ms != null ? d.clip_load_ms : timings.clip_load_ms;
    var hasIndividualLoads = (unetMs != null || vaeMs != null || clipMs != null);
    if (hasIndividualLoads) {
      var maxLoad = Math.max(unetMs || 0, vaeMs || 0, clipMs || 0);
      if (maxLoad > 0) {
        var sourceParts = [];
        if (unetMs != null) sourceParts.push("unet_load_ms=" + unetMs);
        if (vaeMs != null) sourceParts.push("vae_load_ms=" + vaeMs);
        if (clipMs != null) sourceParts.push("clip_load_ms=" + clipMs);
        addStage("Model / CLIP Load", maxLoad, "max(" + sourceParts.join(", ") + ")");
      }
    } else {
      var legacyCl = firstValue("clip_load");
      if (legacyCl) addStage("Model / CLIP Load", legacyCl.value, legacyCl.source);
    }
  }

  // 8. Prompt Encoding (child)
  var pe = firstValue("clip_encode_ms", "clip_encode");
  if (pe) addStage("Prompt Encoding", pe.value, pe.source);

  // 9. Sampling (child)
  var samp = firstValue("sampling_ms", "sampler");
  if (samp) addStage("Sampling", samp.value, samp.source);

  // 10. VAE Decode (child)
  var vae = firstValue("vae_decode_ms", "vae_decode");
  if (vae) addStage("VAE Decode", vae.value, vae.source);

  // 11. Image / Output I/O (child, combined canonical, then legacy)
  var ioMs = d.image_io_ms != null ? d.image_io_ms : timings.image_io_ms;
  var outMs = d.output_transfer_ms != null ? d.output_transfer_ms : timings.output_transfer_ms;
  if (ioMs != null || outMs != null) {
    var ioCombined = (ioMs || 0) + (outMs || 0);
    if (ioCombined > 0) addStage("Image / Output I/O", ioCombined, "image_io_ms + output_transfer_ms");
  } else {
    var legacyIo = firstValue("image_io");
    if (legacyIo) {
      addStage("Image / Output I/O", legacyIo.value, legacyIo.source);
    } else {
      var outputCollectionMs = traceDerived.output_collection_total_ms;
      if (typeof outputCollectionMs === "number" && outputCollectionMs > 0) {
        addStage("Image / Output I/O", outputCollectionMs, "trace.derived_ms.output_collection_total_ms");
      }
    }
  }

  // 12. Output Delivery (local materialization wall time)
  var lm = firstValue("local_output_materialization_ms", "history_finalization_ms");
  if (lm) addStage("Output Delivery", lm.value, lm.source);

  // 13. Scheduler Execution (local wall, parent/non-additive)
  var se = firstValue("scheduler_execution_ms");
  if (se) {
    addStage("Scheduler Execution (local wall)", se.value, se.source);
  } else {
    var legacyGen = firstValue("generation_ms");
    if (legacyGen) {
      addStage("Legacy scheduler wall time", legacyGen.value, legacyGen.source);
    }
  }

  // ── Sort in canonical order ────────────────────────────────────────
  var order = [
    "End-to-End Total",
    "Local Preparation",
    "Remote Invocation Setup",
    "Platform Pre-Restore (inferred)",
    "Snapshot / Runtime Restore",
    "Request Execution",
    "Model / CLIP Load",
    "Prompt Encoding",
    "Sampling",
    "VAE Decode",
    "Image / Output I/O",
    "Output Delivery",
    "Scheduler Execution (local wall)",
    "Legacy scheduler wall time",
  ];
  stages.sort(function (a, b) {
    var ai = order.indexOf(a.label);
    var bi = order.indexOf(b.label);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });

  return stages;
}

/**
 * Build advanced timing diagnostics for expandable display.
 *
 * Secondary to the summary — includes trace version, timing quality/reason,
 * missing fields, raw deltas_ms, derived stages, wall_clock_trace,
 * scheduler_trace, and sources.
 *
 * @param {object} timings - Raw timings/trace object.
 * @param {Array} stages - Normalized timing stages (from normalizeTimingStages).
 * @returns {object}
 */
export function normalizeAdvancedTimingDiagnostics(timings, stages) {
  if (!timings || typeof timings !== "object") {
    return {
      traceVersion: null,
      timingQuality: "missing",
      timingReason: "No timing data",
      missingFields: [],
      rawDeltasMs: null,
      derivedStages: [],
      wallClockTrace: null,
      schedulerTrace: null,
      sources: {},
    };
  }

  var d = timings.deltas_ms || timings;
  var trace = timings.trace || {};
  var traceStages = _timingTraceStages(timings);
  var traceDerived = _timingTraceDerived(timings);
  var traceE2eMs = _deriveTraceEndToEndMs(timings);

  // ── Trace version — read exact version, never fabricate ────────────
  var traceVersion = trace.trace_version
    || timings.trace_version
    || (timings.wall_clock_trace && (timings.wall_clock_trace.trace_version || timings.wall_clock_trace.profile_version))
    || null;

  // ── Semantic alternative groups for missing field detection ────────
  // Instead of an exact canonical field list, group related keys so a
  // single field can satisfy its semantic group.
  var semanticGroups = [
    { group: "end-to-end", keys: ["end_to_end_total_ms", "modal_to_browser"] },
    { group: "queue", keys: ["studio_queue_ms", "queue_ms", "t0_to_t1"] },
    { group: "validation", keys: ["workflow_validation_ms", "remote_validation_ms", "t3_to_t3b"] },
    { group: "model load", keys: ["model_load_ms", "unet_load_ms", "vae_load_ms", "clip_load_ms", "unet_load", "vae_load", "clip_load"] },
    { group: "encode", keys: ["clip_encode_ms", "clip_encode"] },
    { group: "sampling", keys: ["sampling_ms", "sampler"] },
    { group: "vae decode", keys: ["vae_decode_ms", "vae_decode"] },
    { group: "image io", keys: ["image_io_ms", "image_io", "output_collection_total_ms"] },
    { group: "remote inference", keys: ["remote_inference_total_ms", "inference_total"] },
    { group: "materialization", keys: ["local_output_materialization_ms", "history_finalization_ms"] },
    { group: "scheduler", keys: ["scheduler_execution_ms", "generation_ms"] },
  ];
  var runType = timings._run_type || "unknown";
  if (
    runType === "unknown"
    && traceStages.browser_run_click != null
    && (traceStages.output_materialized != null || traceStages.t10_local_materialized != null)
    && d.studio_queue_ms == null
    && d.queue_ms == null
    && d.scheduler_execution_ms == null
  ) {
    // Backfill the run type for direct records written before _run_type existed.
    runType = "direct";
  }
  var applicableGroups = semanticGroups.filter(function (sg) {
    return !(runType === "direct" && (sg.group === "queue" || sg.group === "scheduler"));
  });
  var satisfiedGroups = [];
  var missingGroups = [];
  applicableGroups.forEach(function (sg) {
    var found = sg.keys.some(function (k) {
      return d[k] != null || timings[k] != null || traceDerived[k] != null;
    });
    if (sg.group === "end-to-end" && traceE2eMs != null) found = true;
    if (found) {
      satisfiedGroups.push(sg.group);
    } else {
      missingGroups.push(sg.group);
    }
  });

  // ── Timing quality based on semantic groups ────────────────────────
  var totalGroupCount = applicableGroups.length;
  var presentGroupCount = satisfiedGroups.length;
  var timingQuality, timingReason;
  var hasEndToEnd = satisfiedGroups.indexOf("end-to-end") !== -1;

  if (!stages || stages.length === 0) {
    timingQuality = "missing";
    timingReason = "No timing data available";
  } else if (hasEndToEnd && presentGroupCount >= totalGroupCount - 1) {
    timingQuality = "complete";
    timingReason = "All stages present";
  } else if (presentGroupCount >= 4) {
    timingQuality = "degraded";
    timingReason = "Partial data. Missing groups: " + (missingGroups.length > 0 ? missingGroups.join(", ") : "some fields");
  } else if (presentGroupCount >= 1) {
    timingQuality = "minimal";
    timingReason = "Minimal timing data. Only " + presentGroupCount + " of " + totalGroupCount + " applicable semantic groups present";
  } else {
    timingQuality = "missing";
    timingReason = "No canonical timing fields present";
  }

  // ── Source fields that we know how to read (stage label → source field) ──
  var sources = {};
  if (stages) {
    stages.forEach(function (s) { sources[s.label] = s.source; });
  }

  // ── Backend timing_sources as a separate map ───────────────────────
  var backendTimingSources = timings.timing_sources || {};

  // ── Raw data from nested trace or flat timing ──────────────────────
  var rawDeltasMs = trace.deltas_ms || timings.deltas_ms || null;
  var rawDerivedMs = trace.derived_ms || timings.derived_ms || null;
  var rawStages = trace.stages || timings.stages || null;

  return {
    traceVersion: traceVersion,
    timingQuality: timingQuality,
    timingReason: timingReason,
    missingFields: missingGroups.length > 0 ? missingGroups : [],
    rawDeltasMs: rawDeltasMs,
    rawDerivedMs: rawDerivedMs,
    rawStages: rawStages,
    wallClockTrace: timings.wall_clock_trace || null,
    schedulerTrace: timings.scheduler_trace || null,
    sources: sources,
    backendTimingSources: backendTimingSources,
  };
}

/**
 * Normalize per-node timings if available.
 * @param {object} timings - Raw timings/trace object.
 * @returns {Array<{nodeId:string, durationMs:number, cached:boolean}>}
 */
export function normalizePerNodeTimings(timings) {
  if (!timings || typeof timings !== "object") return [];
  const perNode = timings.per_node || timings.node_times || timings.nodeTimings || {};
  if (Object.keys(perNode).length === 0) return [];

  return Object.entries(perNode).map(function (_ref) {
    var nodeId = _ref[0];
    var data = _ref[1];
    if (typeof data === "number") {
      return { nodeId: nodeId, durationMs: data, cached: false };
    }
    return {
      nodeId: nodeId,
      durationMs: data.duration_ms || data.duration || 0,
      cached: !!data.cached,
    };
  }).sort(function (a, b) {
    return b.durationMs - a.durationMs;
  });
}

/**
 * Build a timing summary string from stages.
 * @param {Array} stages
 * @returns {string}
 */
export function buildTimingSummary(stages) {
  if (!stages || stages.length === 0) return "";
  var total = stages.filter(function (s) { return s.label === "End-to-End Total"; });
  var primary = total.length > 0 ? total[0] : stages[stages.length - 1];
  var topStages = stages.filter(function (s) {
    return s.label !== "End-to-End Total" && s.durationMs > 0;
  }).sort(function (a, b) { return b.durationMs - a.durationMs; }).slice(0, 3);

  var parts = [_formatDuration(primary.durationMs)];
  topStages.forEach(function (s) {
    parts.push(s.label + ": " + _formatDuration(s.durationMs));
  });
  return parts.join(" | ");
}

export function _formatDuration(ms) {
  if (ms == null) return "?";
  if (ms < 1000) return ms.toFixed(0) + "ms";
  if (ms < 60000) return (ms / 1000).toFixed(1) + "s";
  var m = Math.floor(ms / 60000);
  var s = (ms % 60000) / 1000;
  return m + "m " + s.toFixed(0) + "s";
}

// ── Annotation normalization ─────────────────────────────────────────────
//
// Annotations (favorite, note) are stored in extra.annotations or
// extra.metadata.annotations on the raw run.

/**
 * Extract annotation fields from a raw run.
 * @param {object} run - Raw run-history entry.
 * @returns {{favorite: boolean, note: string, noteUpdatedAt: string}}
 */
export function normalizeAnnotations(run) {
  if (!run) return { favorite: false, note: "", noteUpdatedAt: "" };
  var extra = (run && run.extra) || {};
  // Prefer top-level run.annotations (backend stores annotations at this level),
  // then fall back to legacy extra.annotations / extra.metadata.annotations.
  var annotations = run.annotations || extra.annotations || extra.metadata?.annotations || {};
  if (!run.annotations && !extra.annotations && !extra.metadata?.annotations) {
    annotations = {
      favorite: run.favorite,
      note: run.note,
      updated_at: run.note_updated_at || run.noteUpdatedAt,
    };
  }

  return {
    favorite: nilTo(annotations.favorite, false),
    note: nilTo(annotations.note, ""),
    noteUpdatedAt: nilTo(annotations.updated_at || annotations.note_updated_at || annotations.noteUpdatedAt, ""),
  };
}

// ── Image URL resolution ─────────────────────────────────────────────────

/**
 * Resolve the best available image URL for a run, or null.
 * @param {object} run - A run-history entry.
 * @param {string} apiBase - API base path (e.g. "/comfymodal").
 * @returns {string|null}
 */
export function resolveRunImageUrl(run, apiBase) {
  if (!run) return null;
  const extra = (run && run.extra) || {};

  // 1. primary_asset_id (from experiment materialization)
  const primaryAssetId = extra.primary_asset_id || run.primary_asset_id || "";
  if (primaryAssetId) {
    return apiBase + "/assets/" + encodeURIComponent(primaryAssetId);
  }

  // 2. run-level asset_id (from ordinary runs)
  const assetId = run.asset_id || extra.asset_id || "";
  if (assetId) {
    return apiBase + "/assets/" + encodeURIComponent(assetId);
  }

  // 3. output_path (fallback for older runs without asset registration)
  const outputPath = run.output_path || extra.output_path || run.primary_image_path || "";
  if (outputPath) {
    const normalizedPath = String(outputPath).replace(/\\/g, "/");
    const filename = normalizedPath.split("/").pop();
    if (filename) {
      if (/\/output\//i.test(normalizedPath)) {
        return "/view?filename=" + encodeURIComponent(filename) + "&type=output";
      }
      return apiBase + "/studio/outputs/" + encodeURIComponent(filename);
    }
  }

  return null;
}

/**
 * Check whether a run has any resolvable image URL.
 * @param {object} run
 * @returns {boolean}
 */
export function hasRunImage(run) {
  return resolveRunImageUrl(run, "") !== null;
}

/**
 * Normalize generation settings from resolved+requested controls.
 *
 * Returns a unified flat object where resolved values take priority over
 * requested fallbacks.  Preserves zero/false values.  Handles field aliases:
 *   - cfg / guidance  (both accepted, cfg preferred when both exist)
 *   - sampler / sampler_name
 *
 * @param {object} resolved - Resolved controls (runtime-derived values).
 * @param {object} requested - Requested controls (submission values).
 * @returns {object}
 */
export function normalizeGenerationSettings(resolved, requested) {
  var resolved_ = resolved || {};
  var requested_ = requested || {};
  var result = {};

  // All resolved keys pass through (arbitrary keys like "prompt" survive)
  for (var k in resolved_) {
    if (Object.prototype.hasOwnProperty.call(resolved_, k)) {
      result[k] = resolved_[k];
    }
  }

  // Canonical fallback keys with alias mapping.
  // For these keys: resolved values win, but if absent, fall back to
  // requested values (checking aliases).
  // Each entry: [key, [resolvedAliases...], [requestedAliases...]]
  var fallbackKeys = [
    ["seed", ["seed"], ["seed"]],
    ["steps", ["steps"], ["steps"]],
    ["cfg", ["cfg", "guidance"], ["cfg", "guidance"]],
    ["guidance", ["guidance", "cfg"], ["guidance", "cfg"]],
    ["sampler", ["sampler", "sampler_name"], ["sampler", "sampler_name"]],
    ["sampler_name", ["sampler_name", "sampler"], ["sampler_name", "sampler"]],
    ["scheduler", ["scheduler"], ["scheduler"]],
    ["denoise", ["denoise"], ["denoise"]],
    ["width", ["width"], ["width"]],
    ["height", ["height"], ["height"]],
  ];

  fallbackKeys.forEach(function (entry) {
    var key = entry[0];
    var resolvedAliases = entry[1];
    var requestedAliases = entry[2];
    var val;
    var alreadySet = result[key] !== undefined;

    // Check resolved aliases first (skip if already set from resolved loop)
    if (!alreadySet) {
      for (var i = 0; i < resolvedAliases.length; i++) {
        var a = resolvedAliases[i];
        if (resolved_[a] != null) {
          val = resolved_[a];
          break;
        }
      }
    }

    // If still not found and not already set, fall back to requested aliases
    if (val === undefined && !alreadySet) {
      for (var j = 0; j < requestedAliases.length; j++) {
        var b = requestedAliases[j];
        if (requested_[b] != null) {
          val = requested_[b];
          break;
        }
      }
    }

    if (val !== undefined) {
      result[key] = val;
    }
  });

  return result;
}

/**
 * Normalize a raw run-history entry into a stable object with all known fields.
 * Tolerates older records and field aliases (run_id, state, created, etc.).
 * @param {object|null|undefined} rawRun - A raw run-history entry.
 * @param {string} apiBase - API base path (e.g. "/comfymodal").
 * @returns {object|null}
 */
export function normalizeStudioRun(rawRun, apiBase) {
  if (!rawRun) return null;
  const extra = (rawRun && rawRun.extra) || {};
  const run = rawRun;

  // Core identifiers — handle aliases
  const id = run.id || run.run_id || extra.experiment_id || "";
  const kind = run.kind || run.type || extra.kind || "";
  const cellExperimentId = typeof id === "string" && id.indexOf("cell_") === 0
    ? id.slice(5, Math.max(5, id.lastIndexOf("_")))
    : "";
  const experimentId = run.experiment_id || run.experimentId || extra.experiment_id || cellExperimentId;
  const status = run.status || run.state || "unknown";
  const imageUrl = resolveRunImageUrl(run, apiBase);
  const outputPath = run.output_path || extra.output_path || "";

  // Studio metadata
  const studioMeta = extra.studio_meta || extra.studio_metadata || {};
  const presetId = extra.studio_preset_id || studioMeta.studio_preset_id || "";
  const presetLabel = extra.studio_preset_label
    || extra.preset_label
    || run.preset_label
    || studioMeta.studio_preset_label
    || "";
  const snapshotId = extra.studio_snapshot_id || studioMeta.studio_snapshot_id || "";
  const featureId = extra.studio_feature_id || studioMeta.studio_feature_id || "";

  // Prompt fields (use nilTo to preserve empty string)
  const prompt = nilTo(extra.prompt, nilTo(run.prompt, ""));
  const negativePrompt = nilTo(extra.negative_prompt, nilTo(run.negative_prompt, ""));

  // Controls
  const flatControls = {
    prompt: run.prompt,
    negative_prompt: run.negative_prompt,
    seed: run.seed,
    steps: run.steps,
    guidance: run.guidance,
    sampler: run.sampler,
    scheduler: run.scheduler,
  };
  const resolvedControls = extra.resolved_controls || run.resolved_controls || flatControls;
  const requestedControls = extra.requested_controls || extra.controls || run.controls || flatControls;

  // Timestamps
  const startedAt = run.started_at || run.created_at || run.timestamp || run.created || "";
  const completedAt = run.completed_at || "";

  // Timings detail: prefer timing_summary (merged from timing.json by backend)
  // if it is non-empty, fall back to legacy run.timings / extra.timings.
  // Previously required scheduler_execution_ms to be present; now any non-empty
  // timing_summary is preferred.
  const timingSummaryFromBackend = run.timing_summary || {};
  const hasNonEmptyTimingSummary = typeof timingSummaryFromBackend === "object" && Object.keys(timingSummaryFromBackend).length > 0;
  const timings = hasNonEmptyTimingSummary
    ? timingSummaryFromBackend
    : (run.timings || extra.timings || {});

  // Duration: prefer explicit duration_ms, then end_to_end_total_ms,
  // then timings.total_ms (canonical backend field),
  // then legacy run.duration (seconds → ms), else 0.
  // Use nilZero to preserve 0 values rather than falling back to || chains.
  let durationMs = nilZero(run.duration_ms);
  if (!durationMs && timings.end_to_end_total_ms != null) {
    durationMs = timings.end_to_end_total_ms;
  }
  if (!durationMs && timings.total_ms != null) {
    durationMs = timings.total_ms;
  }
  if (!durationMs && run.duration != null) {
    durationMs = typeof run.duration === "number" ? run.duration * 1000 : 0;
  }

  // Workflow hash
  const workflowHash = run.workflow_hash || extra.workflow_hash || "";

  // Error
  const error = nilTo(run.error, nilTo(extra.error, ""));

  // ── Annotations (favorite, note) ────────────────────────────────────
  const annotations = normalizeAnnotations(rawRun);
  const favorite = annotations.favorite;
  const note = annotations.note;
  const noteUpdatedAt = annotations.noteUpdatedAt;

  // ── Timing normalization ────────────────────────────────────────────
  const timingStages = normalizeTimingStages(timings);
  const normalizedEndToEnd = timingStages.find(function (stage) {
    return stage.label === "End-to-End Total";
  });
  if (!durationMs && normalizedEndToEnd) {
    durationMs = normalizedEndToEnd.durationMs;
  }
  const perNodeTimings = normalizePerNodeTimings(timings);
  const advancedTimingDiagnostics = normalizeAdvancedTimingDiagnostics(timings, timingStages);

  // Build timing_sources from both top-level timing_sources annotation
  // and the canonical fields we know how to read.
  const backendTimingSources = timings.timing_sources || rawRun.timing_summary?.timing_sources || {};
  const timingSources = {
    ...backendTimingSources,
    duration_ms: "raw",
    timings: "raw",
    stages: "derived",
    per_node: "derived",
  };
  const timingSummary = buildTimingSummary(timingStages);
  const rawTiming = timings;

  return {
    id: id,
    kind: kind,
    experimentId: experimentId,
    status: status,
    imageUrl: imageUrl,
    outputPath: outputPath,
    presetId: presetId,
    presetLabel: presetLabel,
    snapshotId: snapshotId,
    featureId: featureId,
    prompt: prompt,
    negativePrompt: negativePrompt,
    resolvedControls: resolvedControls,
    requestedControls: requestedControls,
    startedAt: startedAt,
    completedAt: completedAt,
    durationMs: durationMs,
    timings: timings,
    workflowHash: workflowHash,
    error: error,
    raw: rawRun,

    // Annotations (same format for Playground + History)
    favorite: favorite,
    note: note,
    noteUpdatedAt: noteUpdatedAt,

    // Timing summaries
    timingSummary: timingSummary,
    timingStages: timingStages,
    perNodeTimings: perNodeTimings,
    timingSources: timingSources,
    rawTiming: rawTiming,

    // Advanced timing diagnostics (secondary to summary)
    advancedTiming: advancedTimingDiagnostics,
    _timingQuality: advancedTimingDiagnostics.timingQuality,
  };
}
