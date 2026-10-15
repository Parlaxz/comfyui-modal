// Modal Studio — Phase 9 Guidance frontend logic (pure, DOM-free).
//
// Generic structural guidance state machine + manual-mapping helpers. No
// model-family/provider branches anywhere: modes are generic strings,
// mechanisms come from the IMPLEMENTED list only, controller checkpoints
// come from installed Model Library records, preprocessor node types come
// from installed object_info classes with a structural IMAGE-slot shape,
// and anchors come from a structural walk of the API prompt graph. The
// backend revalidates everything authoritatively at execution time; this
// module is the honest advisory/UI layer.
//
// No browser, no DOM, no network: callers inject lists (library records,
// object_info, api prompt) and this module decides. Plain Node-importable
// for FAST_UNIT tests.

// ── Vocabulary (generic; mirrors studio_guidance.py, never extended here) ──

export const GUIDANCE_MODES = Object.freeze(["canny", "depth", "pose"]);

export const GUIDANCE_MECHANISMS = Object.freeze(["CONTROLNET_CONDITIONING"]);

export const GUIDANCE_CONTROLLER_FOLDER = "controlnet";

export const GUIDANCE_DEFAULT_CONDITIONING = Object.freeze({
  strength: 0.7,
  start: 0.0,
  end: 0.8,
});

export const GUIDANCE_STATE_IDS = Object.freeze([
  "off",
  "resolving",
  "known_unconfirmed",
  "known_confirmed",
  "unknown_model",
  "stale",
  "blocked_dependency",
  "unsupported_mode",
  "incompatible_workflow",
  "ready",
]);

// ── Small helpers ───────────────────────────────────────────────────────────

function _str(value) {
  return value == null ? "" : String(value);
}

export function normalizeGuidanceMode(mode) {
  return _str(mode).trim().toLowerCase();
}

export function isSupportedGuidanceMode(mode) {
  return GUIDANCE_MODES.indexOf(normalizeGuidanceMode(mode)) !== -1;
}

export function shortHash(sha) {
  const s = _str(sha).trim().toLowerCase();
  return s ? s.slice(0, 12) : "";
}

/** Display-only model identity: exact short hash + filename as context. */
export function formatModelIdentity(identity) {
  const id = identity && typeof identity === "object" ? identity : {};
  const sha = _str(id.sha || id.model_sha256);
  const filename = _str(id.filename);
  const folder = _str(id.folder);
  const short = shortHash(sha);
  const where = folder ? folder + " / " + filename : filename;
  return {
    shortHash: short,
    filename,
    folder,
    label: short ? "sha256:" + short + (where ? " · " + where : "") : where,
  };
}

// ── Installed-artifact listings (generic filters, no family knowledge) ─────

/**
 * Controller checkpoints: Model Library records from the generic
 * controlnet model folder. Sorted by filename. Never reads names for
 * decisions — the folder equality is environment taxonomy, not a
 * family branch.
 */
export function listControllerCheckpoints(libraryRecords) {
  if (!Array.isArray(libraryRecords)) return [];
  const out = [];
  for (const rec of libraryRecords) {
    if (!rec || typeof rec !== "object") continue;
    if (_str(rec.folder) !== GUIDANCE_CONTROLLER_FOLDER) continue;
    const filename = _str(rec.filename);
    if (!filename) continue;
    out.push({
      checkpoint: filename,
      folder: GUIDANCE_CONTROLLER_FOLDER,
      checkpoint_sha256: _str(rec.hash),
    });
  }
  out.sort((a, b) => (a.checkpoint < b.checkpoint ? -1 : a.checkpoint > b.checkpoint ? 1 : 0));
  return out;
}

function _slotType(decl) {
  if (typeof decl === "string") return decl;
  if (Array.isArray(decl) && decl.length > 0) {
    const first = decl[0];
    if (typeof first === "string") return first;
    if (Array.isArray(first) && first.length > 0 && typeof first[0] === "string") return first[0];
    return "";
  }
  if (decl && typeof decl === "object") {
    return typeof decl.type === "string" ? decl.type : "";
  }
  return "";
}

function _classHasImageSlot(spec) {
  if (!spec || typeof spec !== "object") return false;
  const block = spec.input && typeof spec.input === "object" ? spec.input : {};
  for (const section of ["required", "optional"]) {
    const part = block[section];
    if (!part || typeof part !== "object") continue;
    for (const decl of Object.values(part)) {
      if (_slotType(decl).toUpperCase() === "IMAGE") return true;
    }
  }
  return false;
}

/**
 * Preprocessor node candidates: installed object_info classes exposing an
 * IMAGE-typed input slot (structural shape). Sorted. No name lists.
 */
export function listPreprocessorCandidates(objectInfo) {
  if (!objectInfo || typeof objectInfo !== "object") return [];
  const out = [];
  for (const classType of Object.keys(objectInfo)) {
    if (!classType) continue;
    try {
      if (_classHasImageSlot(objectInfo[classType])) out.push(classType);
    } catch (_e) {
      // A malformed spec never blocks the listing.
    }
  }
  out.sort();
  return out;
}

function _classInputSlots(spec) {
  const merged = {};
  if (!spec || typeof spec !== "object") return merged;
  const block = spec.input && typeof spec.input === "object" ? spec.input : {};
  for (const section of ["required", "optional"]) {
    const part = block[section];
    if (!part || typeof part !== "object") continue;
    for (const name of Object.keys(part)) {
      if (!(name in merged)) merged[name] = part[name];
    }
  }
  return merged;
}

const _STRING_SLOT_TYPES = Object.freeze(["STRING", "COMBO"]);

/**
 * Controller-loader candidates: installed classes with a checkpoint
 * filename input slot (STRING/COMBO-typed or filename-hinted name).
 * Structural shape only; sorted.
 */
export function listLoaderCandidates(objectInfo) {
  if (!objectInfo || typeof objectInfo !== "object") return [];
  const out = [];
  for (const classType of Object.keys(objectInfo)) {
    if (!classType) continue;
    try {
      const slots = _classInputSlots(objectInfo[classType]);
      const hit = Object.keys(slots).some(function (name) {
        if (_STRING_SLOT_TYPES.indexOf(_slotType(slots[name]).toUpperCase()) !== -1) return true;
        const lowered = String(name).toLowerCase();
        return lowered.includes("name") || lowered.includes("path") || lowered.includes("file");
      });
      if (hit) out.push(classType);
    } catch (_e) {
      // A malformed spec never blocks the listing.
    }
  }
  out.sort();
  return out;
}

/**
 * Apply-node candidates: installed classes exposing CONTROL_NET,
 * CONDITIONING, and IMAGE input slots plus a strength slot (the
 * CONTROLNET_CONDITIONING slot contract). Structural shape only; sorted.
 */
export function listApplyCandidates(objectInfo) {
  if (!objectInfo || typeof objectInfo !== "object") return [];
  const out = [];
  for (const classType of Object.keys(objectInfo)) {
    if (!classType) continue;
    try {
      const slots = _classInputSlots(objectInfo[classType]);
      const types = {};
      for (const name of Object.keys(slots)) {
        types[_slotType(slots[name]).toUpperCase()] = true;
      }
      const names = Object.keys(slots);
      const hasControl = types.CONTROL_NET || names.indexOf("control_net") !== -1;
      const hasImage = types.IMAGE || names.indexOf("image") !== -1;
      const hasCond = types.CONDITIONING || names.indexOf("conditioning") !== -1;
      if (hasControl && hasImage && hasCond && names.indexOf("strength") !== -1) {
        out.push(classType);
      }
    } catch (_e) {
      // A malformed spec never blocks the listing.
    }
  }
  out.sort();
  return out;
}

// ── Anchor discovery (structural walk, mirrors the backend contract) ───────

const _ALREADY_CONTROLLED_MARKERS = Object.freeze([
  "controlnet",
  "control_lora",
  "controllora",
  "modelpatch",
  "ipadapter",
  "kontext",
]);

function _asLink(value) {
  if (Array.isArray(value) && value.length >= 2) {
    const nodeId = value[0];
    const index = value[1];
    if (
      (typeof nodeId === "string" || typeof nodeId === "number") &&
      typeof index === "number" &&
      !Number.isNaN(index)
    ) {
      return { node_id: String(nodeId), output: index };
    }
  }
  return null;
}

function _nodeInputs(node) {
  if (node && typeof node === "object" && node.inputs && typeof node.inputs === "object") {
    return node.inputs;
  }
  return {};
}

/**
 * Structural anchor discovery over an API-format prompt graph
 * ({nodeId: {class_type, inputs}}). Returns either
 * {ok:true, anchors:{sampler_id, sampler_class, positive, negative, model,
 * binding_id}} or {ok:false, reason, detail, candidates}. Reason strings
 * match the backend refusal vocabulary so advisory UI and enforcement agree.
 */
export function discoverGuidanceAnchors(apiPrompt) {
  if (!apiPrompt || typeof apiPrompt !== "object" || Object.keys(apiPrompt).length === 0) {
    return { ok: false, reason: "no_sampler", detail: "The workflow has no nodes.", candidates: [] };
  }
  for (const nodeId of Object.keys(apiPrompt)) {
    const node = apiPrompt[nodeId];
    if (!node || typeof node !== "object") continue;
    const lowered = _str(node.class_type).toLowerCase();
    for (const marker of _ALREADY_CONTROLLED_MARKERS) {
      if (lowered.indexOf(marker) !== -1) {
        return {
          ok: false,
          reason: "already_controlled",
          detail:
            "Node " + nodeId + " (" + _str(node.class_type) + ") already carries " +
            "guidance-type conditioning with unclear composition order; refusing to chain automatically.",
          candidates: [],
        };
      }
    }
  }
  const standards = [];
  for (const nodeId of Object.keys(apiPrompt)) {
    const node = apiPrompt[nodeId];
    if (!node || typeof node !== "object") continue;
    const inputs = _nodeInputs(node);
    if ("positive" in inputs && "negative" in inputs) {
      standards.push({ node_id: String(nodeId), class_type: _str(node.class_type) });
    }
  }
  if (standards.length > 1) {
    return {
      ok: false,
      reason: "multiple_samplers",
      detail: "More than one generation sampler is present; confirm which one to guide.",
      candidates: standards,
    };
  }
  if (standards.length === 0) {
    const customs = [];
    for (const nodeId of Object.keys(apiPrompt)) {
      const node = apiPrompt[nodeId];
      if (!node || typeof node !== "object") continue;
      const inputs = _nodeInputs(node);
      if (
        "conditioning" in inputs ||
        ("model" in inputs && ("samples" in inputs || "latent" in inputs))
      ) {
        customs.push({ node_id: String(nodeId), class_type: _str(node.class_type) });
      }
    }
    if (customs.length > 0) {
      return {
        ok: false,
        reason: "custom_sampler",
        detail:
          "The generation node does not expose a standard positive/negative " +
          "conditioning contract; refusing to guess.",
        candidates: customs,
      };
    }
    return {
      ok: false,
      reason: "no_sampler",
      detail: "No generation sampler with positive/negative conditioning found.",
      candidates: [],
    };
  }
  const samplerId = standards[0].node_id;
  const sampler = apiPrompt[samplerId];
  const inputs = _nodeInputs(sampler);
  const edges = {};
  for (const slot of ["positive", "negative", "model"]) {
    const link = _asLink(inputs[slot]);
    if (link === null || !(link.node_id in apiPrompt)) {
      const missing = link === null;
      return {
        ok: false,
        reason: slot === "model" ? "model_edge_not_found" : "conditioning_not_found",
        detail: missing
          ? "Sampler " + samplerId + " input '" + slot + "' is not a resolvable link; refusing to guess the conditioning entry."
          : "Sampler " + samplerId + " input '" + slot + "' points at missing node '" + _str(inputs[slot] && inputs[slot][0]) + "'.",
        candidates: [],
      };
    }
    edges[slot] = link;
  }
  return {
    ok: true,
    anchors: {
      sampler_id: samplerId,
      sampler_class: _str(sampler.class_type),
      positive: edges.positive,
      negative: edges.negative,
      model: edges.model,
      binding_id: "anchor:" + samplerId,
    },
  };
}

// ── Conditioning + mapping record builders ──────────────────────────────────

function _isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

/** Numeric conditioning; user-adjustable pre-confirm. Numbers only. */
export function validateConditioning(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const out = {};
  for (const slot of ["strength", "start", "end"]) {
    const value = typeof src[slot] === "string" && src[slot] !== "" ? Number(src[slot]) : src[slot];
    if (!_isFiniteNumber(value)) {
      return { ok: false, error: "conditioning." + slot + " must be a number" };
    }
    out[slot] = value;
  }
  return { ok: true, conditioning: out };
}

function _nonEmpty(value) {
  return _str(value).trim() !== "";
}

/**
 * Assemble the confirm payload from manual-flow inputs. WHITELIST
 * construction: only the generic mapping fields are emitted, so poisoned
 * suggest/evidence/license/source_url/workflow/family hint fields can never
 * alter what is sent to the backend. Returns {ok:true, record} or
 * {ok:false, error}.
 */
export function buildMappingRecord(input) {
  const src = input && typeof input === "object" ? input : {};
  const sha = _str(src.model_sha256 || src.sha).trim().toLowerCase();
  if (!sha) return { ok: false, error: "model identity is required" };
  const mode = normalizeGuidanceMode(src.mode);
  if (GUIDANCE_MODES.indexOf(mode) === -1) {
    return { ok: false, error: "unsupported mode: " + _str(src.mode) };
  }
  const mechanism = _str(src.mechanism).trim();
  if (GUIDANCE_MECHANISMS.indexOf(mechanism) === -1) {
    return { ok: false, error: "mechanism '" + _str(src.mechanism) + "' is not implemented in this Studio version" };
  }
  const checkpoint = _str(src.checkpoint).trim();
  const loader = _str(src.loaderClass || (src.nodes && src.nodes.loader)).trim();
  const apply = _str(src.applyClass || (src.nodes && src.nodes.apply)).trim();
  const preprocessor = _str(src.preprocessorClass || (src.nodes && src.nodes.preprocessor)).trim();
  if (!checkpoint) return { ok: false, error: "controller checkpoint is required" };
  if (!loader || !apply || !preprocessor) {
    return { ok: false, error: "loader, apply, and preprocessor node types are required" };
  }
  const cond = validateConditioning(
    src.conditioning || { strength: src.strength, start: src.start, end: src.end }
  );
  if (!cond.ok) return cond;
  return {
    ok: true,
    record: {
      model_sha256: sha,
      mode,
      mechanism,
      controller: {
        checkpoint,
        folder: _str(src.checkpointFolder || src.folder || GUIDANCE_CONTROLLER_FOLDER).trim() || GUIDANCE_CONTROLLER_FOLDER,
        checkpoint_sha256: _str(src.checkpointSha256).trim().toLowerCase(),
      },
      nodes: { loader, apply, preprocessor },
      conditioning: cond.conditioning,
      evidence: { note: "manual mapping, user-confirmed" },
      confirmed: true,
    },
  };
}

// ── State machine ───────────────────────────────────────────────────────────

/**
 * Resolve the Guidance panel state. Pure: all installedness/anchor evidence
 * arrives via input; nothing is fetched here.
 *
 * input: {
 *   engaged, mode,
 *   identity: null | {status:"resolving"|"resolved"|"unresolvable", sha?, filename?, folder?},
 *   mapping: null | {record, stale?:bool, staleDetail?:string},
 *   mappingUnconfirmed?: bool,
 *   missingDependencies: [{kind:"checkpoint"|"node"|"preprocessor"|"guide", name}],
 *   anchors: null | {ok:true, anchors} | {ok:false, reason, detail, candidates},
 *   anchorPick: string (confirmed sampler pick when candidates exist),
 *   guideImage: string,
 *   keepExisting?: bool (user kept a stale mapping explicitly),
 * }
 */
export function resolveGuidanceState(input) {
  const src = input && typeof input === "object" ? input : {};
  const engaged = src.engaged === true;
  const mode = normalizeGuidanceMode(src.mode);
  const guideImage = _str(src.guideImage).trim();
  const anchorPick = _str(src.anchorPick).trim();

  if (!engaged) {
    return {
      state: "off",
      ready: false,
      runGateReason: null,
      snapshot: null,
      headline: "Guidance off",
      detail: "Enable guidance to condition this run on a guide image.",
      actions: [{ id: "enable", label: "Enable guidance" }],
      identity: null,
    };
  }

  if (GUIDANCE_MODES.indexOf(mode) === -1) {
    return {
      state: "unsupported_mode",
      ready: false,
      runGateReason: "Guidance does not support '" + _str(src.mode) + "'",
      snapshot: { engaged: true, ready: false, reason: "unsupported_mode" },
      headline: "Guidance does not support '" + (_str(src.mode) || "this mode") + "'",
      detail: "It supports " + GUIDANCE_MODES.join(", ") + ".",
      actions: [
        { id: "choose_mode", label: "Choose supported mode" },
        { id: "cancel", label: "Cancel" },
      ],
      identity: null,
    };
  }

  const identity = src.identity && typeof src.identity === "object" ? src.identity : null;
  if (!identity || identity.status === "resolving") {
    return {
      state: "resolving",
      ready: false,
      runGateReason: "Checking compatibility…",
      snapshot: { engaged: true, ready: false, reason: "identity_resolving" },
      headline: "Checking compatibility…",
      detail: "Resolving the loaded model identity…",
      actions: [],
      identity: null,
    };
  }

  if (identity.status === "unresolvable") {
    const filename = _str(identity.filename) || "this model";
    return {
      state: "unknown_model",
      ready: false,
      runGateReason: "Guidance unavailable for this model — identity not verified",
      snapshot: { engaged: true, ready: false, reason: "identity_unresolvable" },
      headline: "Guidance unavailable for this model",
      detail:
        "Loaded '" + filename + "', Identity: Not verified. No verified guidance " +
        "mapping was found. Studio will not guess from the filename.",
      actions: [
        { id: "choose_mapping", label: "Choose mapping" },
        { id: "cancel", label: "Cancel" },
      ],
      identity: formatModelIdentity({ sha: "", filename }),
    };
  }

  const formatted = formatModelIdentity({
    sha: identity.sha,
    filename: identity.filename,
    folder: identity.folder,
  });

  const mapping = src.mapping && typeof src.mapping === "object" ? src.mapping : null;
  if (!mapping || !mapping.record) {
    return {
      state: "unknown_model",
      ready: false,
      runGateReason: "Guidance unavailable for this model — no confirmed mapping",
      snapshot: { engaged: true, ready: false, reason: "no_confirmed_mapping" },
      headline: "Guidance unavailable for this model",
      detail:
        "Loaded '" + (formatted.filename || "this model") + "', Identity: " +
        (formatted.shortHash ? "sha256:" + formatted.shortHash : "Not verified") +
        ". No verified guidance mapping was found. Studio will not guess from the filename.",
      actions: [
        { id: "choose_mapping", label: "Choose mapping" },
        { id: "cancel", label: "Cancel" },
      ],
      identity: formatted,
    };
  }

  if (src.mappingUnconfirmed === true) {
    return {
      state: "known_unconfirmed",
      ready: false,
      runGateReason: "Guidance mapping needs confirmation",
      snapshot: { engaged: true, ready: false, reason: "mapping_unconfirmed" },
      headline: "Guidance mapping needs confirmation",
      detail: "A guidance mapping exists for this exact model identity but is not confirmed yet.",
      actions: [
        { id: "confirm_mapping", label: "Confirm mapping" },
        { id: "change", label: "Change" },
      ],
      identity: formatted,
    };
  }

  if (mapping.stale === true && src.keepExisting !== true) {
    return {
      state: "stale",
      ready: false,
      runGateReason: "Previously confirmed mapping needs review",
      snapshot: { engaged: true, ready: false, reason: "stale_mapping" },
      headline: "Previously confirmed mapping needs review",
      detail:
        "The model identity is the same, but this mapping's evidence changed: " +
        (_str(mapping.staleDetail) || "an installed dependency changed") +
        ". Studio will not replace the confirmed mapping automatically.",
      actions: [
        { id: "review_reconfirm", label: "Review and reconfirm" },
        { id: "keep_existing", label: "Keep existing mapping" },
        { id: "cancel", label: "Cancel" },
      ],
      identity: formatted,
    };
  }

  const missing = Array.isArray(src.missingDependencies) ? src.missingDependencies : [];
  if (missing.length > 0) {
    const first = missing[0];
    const kind = _str(first.kind) || "dependency";
    const name = _str(first.name) || "unknown";
    const kindLabel =
      kind === "checkpoint" ? "controller checkpoint" : kind === "guide" ? "guide image" : kind;
    return {
      state: "blocked_dependency",
      ready: false,
      runGateReason: "Guidance cannot run — Missing " + kindLabel + ": '" + name + "'",
      snapshot: { engaged: true, ready: false, reason: "missing_dependency" },
      headline: "Guidance cannot run — Missing " + kindLabel + ": '" + name + "'",
      detail: "The confirmed mapping requires this artifact. Resolve it, change the mapping, or cancel.",
      actions: [
        { id: kind === "checkpoint" ? "find_in_library" : "resolve_dependency", label: kind === "checkpoint" ? "Find in Model Library" : "Resolve dependency" },
        { id: "change", label: "Change mapping" },
        { id: "cancel", label: "Cancel" },
      ],
      identity: formatted,
    };
  }

  const anchors = src.anchors && typeof src.anchors === "object" ? src.anchors : null;
  if (anchors && anchors.ok !== true) {
    const reason = _str(anchors.reason) || "incompatible_workflow";
    const candidates = Array.isArray(anchors.candidates) ? anchors.candidates : [];
    if (reason === "multiple_samplers" && candidates.length > 0 && !anchorPick) {
      return {
        state: "incompatible_workflow",
        ready: false,
        runGateReason: "Guidance anchor is ambiguous — confirm which sampler to guide",
        snapshot: { engaged: true, ready: false, reason },
        headline: "More than one generation sampler is present",
        detail: _str(anchors.detail) || "Confirm which one to guide.",
        actions: [
          { id: "confirm_anchor", label: "Confirm anchor" },
          { id: "cancel", label: "Cancel" },
        ],
        identity: formatted,
        candidates,
      };
    }
    return {
      state: "incompatible_workflow",
      ready: false,
      runGateReason: "Guidance anchor not found: " + reason,
      snapshot: { engaged: true, ready: false, reason },
      headline: "Required guidance anchor not found",
      detail: (_str(anchors.detail) || "The workflow cannot take guidance structurally.") + " No fallback method was selected.",
      actions: [
        { id: "choose_workflow", label: "Choose another workflow" },
        { id: "cancel", label: "Cancel" },
      ],
      identity: formatted,
      candidates,
    };
  }

  if (!guideImage) {
    return {
      state: "known_confirmed",
      ready: false,
      runGateReason: "Guidance is confirmed but needs a guide image",
      snapshot: { engaged: true, ready: false, reason: "guide_image_missing" },
      headline: "Guidance ready",
      detail: "Mapping confirmed for this model identity. Select a guide image to run with guidance.",
      actions: [
        { id: "change", label: "Change" },
        { id: "reconfirm", label: "Reconfirm" },
      ],
      identity: formatted,
    };
  }

  return {
    state: "ready",
    ready: true,
    runGateReason: null,
    snapshot: { engaged: true, ready: true },
    headline: "Guidance ready",
    detail:
      "Guidance will condition this run (" + mode + ", sha256:" + (formatted.shortHash || "?") + ").",
    actions: [
      { id: "change", label: "Change" },
      { id: "reconfirm", label: "Reconfirm" },
    ],
    identity: formatted,
  };
}

/**
 * Snapshot guidance key for run/snapshot payloads: the exact shape
 * studio_models.normalize_snapshot_payload consumes. Null when guidance is
 * not engaged (a plain run). Whitelist-built: engaged/ready/reason only.
 */
export function buildSnapshotGuidance(status) {
  const st = status && typeof status === "object" ? status : null;
  if (!st || st.engaged !== true) return null;
  if (st.ready === true) return { engaged: true, ready: true };
  const reason = _str(st.reason || st.runGateReason || "guidance engaged but not ready");
  return { engaged: true, ready: false, reason: reason.slice(0, 300) };
}

// ── History provenance projection (generic rows, no provider branches) ──────

/**
 * Project generic guidance_provenance fields into [label, value] rows.
 * Renders whatever strings the data holds; absent fields are skipped.
 * Null when no provenance is present (legacy records render nothing).
 */
export function summarizeGuidanceProvenance(provenance) {
  const p = provenance && typeof provenance === "object" && !Array.isArray(provenance)
    ? provenance
    : null;
  if (!p) return null;
  const rows = [];
  const push = (label, value) => {
    const v = value == null ? "" : String(value);
    if (v !== "") rows.push([label, v]);
  };
  push("Mode", p.mode);
  if (p.model_sha256 != null && String(p.model_sha256) !== "") {
    rows.push(["Model identity", "sha256:" + shortHash(p.model_sha256)]);
  }
  push("Mechanism", p.mechanism);
  push("Controller checkpoint", p.controller_checkpoint);
  if (p.controller_checkpoint_sha256 != null && String(p.controller_checkpoint_sha256) !== "") {
    rows.push(["Controller hash", "sha256:" + shortHash(p.controller_checkpoint_sha256)]);
  }
  push("Controller folder", p.controller_folder);
  push("Preprocessor", p.preprocessor);
  if (p.mapping_revision != null && String(p.mapping_revision) !== "") {
    rows.push(["Mapping revision", String(p.mapping_revision)]);
  }
  push("Anchor", p.anchor_binding_id);
  push("Sampler", p.sampler_id);
  if (p.strength != null && String(p.strength) !== "") rows.push(["Strength", String(p.strength)]);
  if (p.start != null && String(p.start) !== "") rows.push(["Start", String(p.start)]);
  if (p.end != null && String(p.end) !== "") rows.push(["End", String(p.end)]);
  push("Refusal reason", p.refusal_reason);
  push("Refusal detail", p.refusal_detail);
  return rows.length > 0 ? rows : null;
}

// ── Studio V3 preset hooks (Phase 12, frontend lane) ─────────────────────
// Narrow snapshot/apply/reset only, over plain guidance-input shapes (the
// resolveGuidanceState input the playground already builds). This module has
// no imports and no fetch by construction, so these hooks CANNOT call
// mapping-save/confirm APIs and NEVER substitute mappings: missing/stale
// mappings hydrate to blocked/manual state via planPresetHydration (web/
// studio-presets.js). Guide images are never snapshotted and never restored.

/**
 * Owner-native guidance snapshot for preset capture. Reads only confirmed-
 * mapping config (mode/mechanism/identity/revision/controller/nodes/
 * conditioning); the guide image is deliberately never read.
 * Shape mirrors the backend guidance section: controller is an object,
 * mapping_revision is an opaque string, model_sha256 is 64-hex-or-empty
 * (enforced downstream by projection).
 * @param {object} input resolveGuidanceState-style input
 * @returns {object|null} owner-native snapshot (allowlist-projected downstream)
 */
export function snapshotGuidanceForPreset(input) {
  const src = input && typeof input === "object" ? input : {};
  if (src.engaged !== true) return { engaged: false };
  const mapping = src.mapping && typeof src.mapping === "object" ? src.mapping : null;
  const record = mapping && mapping.record && typeof mapping.record === "object"
    ? mapping.record
    : null;
  const controller = record && record.controller && typeof record.controller === "object"
    ? record.controller
    : {};
  const nodes = record && record.nodes && typeof record.nodes === "object" ? record.nodes : {};
  const conditioning = record && record.conditioning && typeof record.conditioning === "object"
    ? record.conditioning
    : src.conditioning && typeof src.conditioning === "object"
      ? src.conditioning
      : {};
  const sha = _str(
    (src.identity && src.identity.sha) || (record && record.model_sha256)
  ).trim().toLowerCase();
  const revision = record && record.revision != null
    ? record.revision
    : (record && record.mapping_revision != null ? record.mapping_revision : "");
  return {
    engaged: true,
    mode: normalizeGuidanceMode(src.mode),
    mechanism: _str(src.mechanism || (record && record.mechanism)).trim(),
    model_sha256: /^[0-9a-f]{64}$/.test(sha) ? sha : "",
    mapping_revision: revision == null ? "" : String(revision),
    controller: {
      checkpoint: _str(controller.checkpoint).trim(),
      folder: _str(controller.folder || controller.checkpointFolder).trim(),
      checkpoint_sha256: _str(controller.checkpoint_sha256 || controller.checkpointSha256).trim().toLowerCase(),
    },
    nodes: {
      loader: _str(nodes.loader).trim(),
      apply: _str(nodes.apply).trim(),
      preprocessor: _str(nodes.preprocessor).trim(),
    },
    conditioning: {
      strength: conditioning.strength,
      start: conditioning.start,
      end: conditioning.end,
    },
  };
}

/**
 * Apply a preset guidance section onto a guidance-input draft. Returns a new
 * input object; never writes mappings, never confirms anything. Missing or
 * stale mappings are left for planPresetHydration to block (manual state).
 * @param {object} current current guidance input (or null)
 * @param {object} section preset guidance section (or null for neutral)
 * @returns {object} next guidance input
 */
export function applyGuidanceFromPreset(current, section) {
  const base = current && typeof current === "object" ? Object.assign({}, current) : {};
  const s = section && typeof section === "object" ? section : null;
  if (!s || s.engaged !== true) {
    base.engaged = false;
    return base;
  }
  base.engaged = true;
  if (s.mode) base.mode = s.mode;
  // Identity/mapping re-resolve live at load time from the stored sha; the
  // confirmed record itself is never carried (no substitution, no confirm).
  base.presetModelSha256 = String(s.model_sha256 || "");
  base.presetMappingRevision = s.mapping_revision != null ? String(s.mapping_revision) : "";
  if (s.conditioning && typeof s.conditioning === "object") {
    base.conditioning = {
      strength: s.conditioning.strength,
      start: s.conditioning.start,
      end: s.conditioning.end,
    };
  }
  return base;
}

/** Neutral (disengaged) guidance input for omitted-section reset. */
export function resetGuidanceForPreset(current) {
  const base = current && typeof current === "object" ? Object.assign({}, current) : {};
  base.engaged = false;
  delete base.presetModelSha256;
  delete base.presetMappingRevision;
  return base;
}
