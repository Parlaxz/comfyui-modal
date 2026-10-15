// Modal Studio — V3 Presets (Phase 12, frontend lane)
//
// DOM-free, independently testable preset state core. No DOM, no fetch, no
// localStorage, no imports — pure projection/validation/hydration planning.
//
// Server contract (backend lane owns studio_domain/preset_state.py; this
// module mirrors it — the server stays the authority, this is a pre-check):
// REST under /comfymodal/studio/workflows —
//   GET|POST /versions/{vid}/presets
//   GET|PATCH|DELETE /presets/{pid}
//   POST /presets/{pid}/duplicate
//   POST /presets/{pid}/copy-to-version
// Record: {preset_id, workflow_version_id, name, description, tags,
//   studio_state v1, mapping_fingerprint, created_at, updated_at}.
// studio_state v1 root: schema_version=1 + ALL NINE sections required
// (core/styles/layout/methods/references/guidance/sketch/post/output).
// Closed field allowlists per section; the backend rejects unknown keys,
// image-bearing keys/values, and anything over the 64KiB cap.
//
// Section shapes mirror the backend normalizers exactly:
//   core: {positive_prompt*, negative_prompt*, controls{scalars, no
//     source_image/mask}, activeMode*, activeSubtool*, skipTextGenerate*}
//   styles: {setId*, selectedId*, basePrompt?}
//   layout: FLAT native {high_level_description?, background?, style_mode?,
//     aesthetics?, lighting?, photo?, medium?, art_style?, color_palette?
//     (STRING), width?, height?, bgBrightness?, boxes?[{id*, type?, x?, y?,
//     w?, h?, desc?, text?, color_palette? (STRING), nobbox?, locked?}]}
//   methods: {inpaintMethod? (string|null), inpaintOverride? ({workflow_id,
//     workflow_version_id}|null), expandMethod?, expandOverride?, pad*?}
//   references: {method?, override? (pair|null), cards?[{label* only}]}
//   guidance: {engaged?, mode?, mechanism?, model_sha256? (64-hex|empty),
//     mapping_revision? (STRING), controller? {checkpoint?, folder?,
//     checkpoint_sha256?}, nodes? {loader?, apply?, preprocessor?},
//     conditioning? {strength?, start?, end?}}
//   sketch: {tool?, brushSize?, opacity?, hardness?, color?, bgColor?,
//     width?, height?}
//   post: {recipe? ({curves?, mixer?, grading?, crop?, format?, quality?,
//     embedMetadata?, embed_metadata?} — scalars-or-null only)}
//   output: FLAT {output_format?, quality?, webp_lossless_compression?
//     (bool), auto_save_local?, save_folder? (relative), save_metadata_sidecar?,
//     preview_*: scalar} — no nested save/preview objects, no data_saver_*.
//
// Two entry points:
//   capturePresetState(ownerSnapshots) -> detached v1 state via explicit
//     allowlist projection (never clone-then-delete). ALWAYS emits all nine
//     sections (neutral for absent owners) because the backend requires them.
//   planPresetHydration(state, targetContext) -> {sections, issues[]} with
//     blocking validation issues.
//
// Images (sources, masks, reference files, guides, sketch pixels, history,
// compare slots, outputs, data:/blob: URLs, base64) are NEVER captured and
// NEVER hydrated. Omitted sections hydrate to neutral (never inherit).

export const PRESET_SCHEMA_VERSION = 1;
export const PRESET_STATE_MAX_BYTES = 64 * 1024;

// String cap mirrors the backend per-string cap (8 KiB) so capture is
// lossless for backend-valid states — truncation only ever drops bytes the
// server would reject anyway.
export const PRESET_STRING_MAX = 8 * 1024;

export const PRESET_SECTIONS = Object.freeze([
  "core",
  "styles",
  "layout",
  "methods",
  "references",
  "guidance",
  "sketch",
  "post",
  "output",
]);

// Frontend-known value lists (informational only — the backend shape layer
// accepts any string here, so projection NEVER wipes unknown values; stale/
// unsupported values are handled at plan time with bounded warnings).
export const PRESET_ACTIVE_MODES = Object.freeze(["generate", "edit", "post"]);
export const PRESET_INPAINT_METHODS = Object.freeze(["crop_stitch", "conditioning", "dedicated"]);
export const PRESET_EXPAND_METHODS = Object.freeze(["pad", "pad_preserve", "dedicated"]);
export const PRESET_REFERENCE_METHODS = Object.freeze([
  "conditioning_slots",
  "reference_latent_chain",
  "dedicated",
]);
export const PRESET_GUIDANCE_MODES = Object.freeze(["canny", "depth", "pose"]);
export const PRESET_GUIDANCE_MECHANISMS = Object.freeze(["CONTROLNET_CONDITIONING"]);
export const PRESET_SKETCH_TOOLS = Object.freeze([
  "brush",
  "pencil",
  "eraser",
  "line",
  "rectangle",
  "circle",
  "fill",
  "eyedropper",
]);
export const PRESET_OUTPUT_FORMATS = Object.freeze(["original", "png", "jpeg", "webp"]);

// Keys that must never appear in a preset (mirrors the backend deny-list
// semantics for nested keys; root section names are exempt by construction —
// validation scans within sections only).
// NOTE: bare "preview", "output", "reference(s)", "crop" are deliberately NOT
// banned: output.preview_* scalars, the references section, and post.recipe
// .crop are legitimate contract fields. Their file/URL variants below stay
// banned, and image-like *values* are still rejected.
export const PRESET_IMAGE_KEYS = Object.freeze([
  "image",
  "images",
  "imageurl",
  "imagedata",
  "source",
  "source_image",
  "sourceimage",
  "mask",
  "maskimage",
  "savedmask",
  "savedmasksource",
  "reference_file",
  "reference_image",
  "file",
  "files",
  "filename",
  "upload",
  "uploads",
  "url",
  "urls",
  "link",
  "links",
  "href",
  "src",
  "blob",
  "dataurl",
  "dataimage",
  "data",
  "base64",
  "pixels",
  "pixel",
  "pixeldata",
  "bitmap",
  "canvas",
  "layer",
  "layers",
  "thumbnail",
  "snapshot",
  "asset",
  "assets",
  "attachment",
  "guideimage",
  "guide",
  "guides",
  "sketchpixels",
  "sketchimage",
  "sketchdata",
  "history",
  "historyid",
  "historyids",
  "runid",
  "experimentid",
  "generationid",
  "compare",
  "compareimage",
  "outputs",
  "outputimage",
  "bbox",
  "boundingbox",
  "cropgeometry",
]);

// Backend value rule: data:/blob:/http(s): prefixes (case-insensitive).
const BACKEND_IMAGE_VALUE_PATTERNS = [
  /^data:/i,
  /^blob:/i,
  /^https?:\/\//i,
];

// Broader capture-time rule (also drops ws(s) and long token blobs so
// capture never stores ambient image pointers; validation uses the backend
// rule above so client pre-checks never block backend-valid states).
const CAPTURE_IMAGE_VALUE_PATTERNS = [
  /^data:/i,
  /^blob:/i,
  /^https?:\/\//i,
  /^ws:\/\/|^wss:\/\//i,
];

function _normKey(key) {
  return String(key == null ? "" : key).toLowerCase().replace(/[_\-\s]/g, "");
}

/** True when a key name is image/history-bearing and must never be captured. */
export function isImageKey(key) {
  const norm = _normKey(key);
  if (!norm) return false;
  for (const banned of PRESET_IMAGE_KEYS) {
    if (norm === banned) return true;
  }
  // Backend substring rule, mirrored: base64/blob/data:image/data_image/url
  // anywhere in the key. Plus conservative compound heuristics for preview/
  // file pointers (previewUrl, referenceFile, maskPreviewId, ...).
  const lowered = String(key == null ? "" : key).toLowerCase();
  if (
    lowered.includes("base64") ||
    lowered.includes("blob") ||
    lowered.includes("data:image") ||
    lowered.includes("data_image") ||
    lowered.includes("url")
  ) {
    return true;
  }
  if (/(image|mask|thumbnail|pixels|bitmap|guideimage|history|compare)/.test(norm)) return true;
  if (/file$/.test(norm)) return true;
  return false;
}

/** Backend value rule: data:/blob:/http(s) payloads. */
export function isBackendImageValue(value) {
  if (typeof value !== "string") return false;
  const v = value.trim();
  if (!v) return false;
  for (const re of BACKEND_IMAGE_VALUE_PATTERNS) {
    if (re.test(v)) return true;
  }
  return false;
}

/**
 * Capture-time rule: backend rule + ws(s) + long tokenless blobs.
 * Used when projecting owner state (drop, never store).
 */
export function isImageLikeValue(value) {
  if (typeof value !== "string") return false;
  const v = value.trim();
  if (!v) return false;
  for (const re of CAPTURE_IMAGE_VALUE_PATTERNS) {
    if (re.test(v)) return true;
  }
  // Long tokenless blobs are base64 payloads, not config.
  if (/^[A-Za-z0-9+/=_-]+$/.test(v) && v.length > 512) return true;
  return false;
}

// ── Small coercion helpers ────────────────────────────────────────────────

function _str(value, max) {
  const cap = max != null ? max : PRESET_STRING_MAX;
  let s = value == null ? "" : String(value);
  if (s.length > cap) s = s.slice(0, cap);
  return s;
}

function _optStr(value, max) {
  if (value == null) return "";
  const s = _str(value, max);
  // Free-text config fields never carry image payloads — drop them instead
  // of capturing (capture is projection-only, never validated here).
  if (isImageLikeValue(s)) return "";
  return s;
}

function _bool(value, fallback) {
  if (value === true || value === 1) return true;
  if (value === false || value === 0) return false;
  return fallback === true;
}

function _num(value, fallback, min, max) {
  if (typeof value === "boolean") return fallback;
  const n = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  if (typeof n !== "number" || !Number.isFinite(n)) return fallback;
  let out = n;
  if (min != null) out = Math.max(min, out);
  if (max != null) out = Math.min(max, out);
  return out;
}

function _strArrayJoin(raw, maxLen) {
  if (typeof raw === "string") return raw.trim() ? raw.slice(0, maxLen) : "";
  if (!Array.isArray(raw)) return "";
  const parts = [];
  for (const item of raw) {
    if (typeof item !== "string" || !item.trim()) continue;
    if (isImageLikeValue(item)) continue;
    parts.push(item.trim());
    if (parts.join(",").length >= maxLen) break;
  }
  return parts.join(",").slice(0, maxLen);
}

const _SHA256_HEX_RE = /^[0-9a-f]{64}$/;

function _sha256OrEmpty(value) {
  const s = _optStr(value, 128).toLowerCase();
  return _SHA256_HEX_RE.test(s) ? s : "";
}

/**
 * Method/reference override pair ({workflow_id, workflow_version_id}|null),
 * mirroring the backend shape. Bare string ids can never satisfy the pair
 * contract, so they degrade to null (the capture layer resolves ids to pairs
 * via the workflow library before projecting).
 */
function _overridePair(value) {
  if (value == null) return null;
  if (typeof value !== "object" || Array.isArray(value)) return null;
  const wid = typeof value.workflow_id === "string" && value.workflow_id ? value.workflow_id : "";
  const ver = typeof value.workflow_version_id === "string" && value.workflow_version_id
    ? value.workflow_version_id
    : "";
  if (!wid || !ver) return null;
  if (isImageLikeValue(wid) || isImageLikeValue(ver)) return null;
  return {
    workflow_id: wid.slice(0, 200),
    workflow_version_id: ver.slice(0, 200),
  };
}

// ── Section projections (explicit allowlists; never clone-then-delete) ────
// Each builder reads ONLY its listed fields off the owner-native input and
// returns a fresh backend-shaped object. Image-bearing input fields are
// ignored, never copied. Unknown input keys are ignored (validation flags
// them on load).

/**
 * Resolve the visible user prompt from an owner-native core input.
 *
 * The shelf prompt editor commits through the validated store, but validation
 * drops schema-unknown roles — on a stale-mapping version the prompt role is
 * absent from the control schema (its node is not in the graph) while scalar
 * roles like seed survive, so committed keystrokes never reach
 * store.controlValues even though the editor keeps showing them. The visible
 * value therefore lives in the structured draft (structured mode) or under
 * either prompt alias (text mode), and capture must read those — never the
 * store alone.
 *
 * Priority: structured composition wins in structured mode (even when empty —
 * clearing the editor must save empty); otherwise the first non-empty alias
 * (positive_prompt, then prompt) wins; empty strings fall through so a clear
 * in one alias cannot mask a value in the other.
 */
export function resolvePresetPrompt(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const parts = src.structuredParts != null
    ? src.structuredParts
    : (src.promptParts != null ? src.promptParts : src.structured);
  const mode = src.promptMode != null ? src.promptMode : src.prompt_mode;
  if (parts && typeof parts === "object" && mode !== "text") {
    const get = (key) => (typeof parts[key] === "string" ? parts[key].trim() : "");
    const composed = [get("subject"), get("style"), get("details"), get("composition")]
      .filter(Boolean)
      .join(", ");
    if (mode === "structured" || composed) return composed;
  }
  const pos = src.positive_prompt != null ? String(src.positive_prompt) : "";
  const bare = src.prompt != null ? String(src.prompt) : "";
  if (pos.trim()) return pos;
  if (bare.trim()) return bare;
  if (src.positive_prompt != null) return pos;
  return bare;
}

function _projectCore(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const controls = {};
  const srcControls = src.controls && typeof src.controls === "object" ? src.controls : {};
  const keys = Object.keys(srcControls).slice(0, 64);
  for (const key of keys) {
    if (!key || isImageKey(key)) continue;
    const value = srcControls[key];
    if (value === undefined || value === null) continue;
    if (typeof value === "string") {
      if (isImageLikeValue(value)) continue;
      controls[key] = value.slice(0, PRESET_STRING_MAX);
    } else if (typeof value === "boolean") {
      controls[key] = value;
    } else if (typeof value === "number" && Number.isFinite(value)) {
      controls[key] = value;
    }
    // Objects/arrays in controls are not scalar config — dropped.
  }
  return {
    positive_prompt: _optStr(resolvePresetPrompt(src)),
    negative_prompt: _optStr(
      src.negative_prompt != null ? src.negative_prompt : src.negativePrompt
    ),
    controls,
    activeMode: _optStr(src.activeMode != null ? src.activeMode : src.mode, 80),
    activeSubtool: _optStr(src.activeSubtool != null ? src.activeSubtool : src.subtool, 80),
    skipTextGenerate: _bool(src.skipTextGenerate, false),
  };
}

function _projectStyles(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const out = {
    setId: _optStr(src.setId != null ? src.setId : src.set_id, 200),
    selectedId: _optStr(src.selectedId != null ? src.selectedId : src.selected_id, 200),
  };
  const base = src.basePrompt != null ? src.basePrompt : src.base_prompt;
  if (base !== undefined) out.basePrompt = _optStr(base);
  return out;
}

let _boxIdCounter = 0;

function _projectLayoutBox(item, index) {
  if (!item || typeof item !== "object") return null;
  const id = typeof item.id === "string" && item.id ? item.id.slice(0, 200) : "box-" + index;
  const num = (v) => (typeof v === "boolean" ? 0 : _num(v, 0));
  return {
    id,
    type: _optStr(item.type != null ? item.type : item.kind, 80),
    x: num(item.x),
    y: num(item.y),
    w: num(item.w),
    h: num(item.h),
    desc: _optStr(item.desc != null ? item.desc : item.label, 2000),
    text: _optStr(item.text, 2000),
    color_palette: _strArrayJoin(
      item.color_palette != null ? item.color_palette : item.color,
      8000
    ),
    nobbox: _bool(item.nobbox, false),
    locked: _bool(item.locked, false),
  };
}

/** Flat native layout shape (mirrors the backend section exactly). */
function _projectLayout(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  // Accept both the flat native draft and the historical nested preset
  // draft ({descriptor, modes, palette, dims}) — both project to flat.
  const modes = src.modes && typeof src.modes === "object" ? src.modes : {};
  const dims = src.dims && typeof src.dims === "object" ? src.dims : {};
  const pick = (flat, nested, legacy) => {
    if (src[flat] !== undefined) return src[flat];
    if (nested && modes[nested] !== undefined) return modes[nested];
    if (legacy && src[legacy] !== undefined) return src[legacy];
    return undefined;
  };
  const boxes = [];
  if (Array.isArray(src.boxes)) {
    for (let i = 0; i < src.boxes.length && boxes.length < 64; i++) {
      const box = _projectLayoutBox(src.boxes[i], i);
      if (box) boxes.push(box);
    }
  }
  const widthRaw = src.width !== undefined ? src.width : dims.width;
  const heightRaw = src.height !== undefined ? src.height : dims.height;
  return {
    high_level_description: _optStr(pick("high_level_description", null, "descriptor"), 8000),
    background: _optStr(pick("background"), 2000),
    style_mode: _optStr(pick("style_mode"), 200),
    aesthetics: _optStr(pick("aesthetics"), 2000),
    lighting: _optStr(pick("lighting"), 2000),
    photo: _optStr(pick("photo"), 2000),
    medium: _optStr(pick("medium"), 2000),
    art_style: _optStr(pick("art_style"), 2000),
    color_palette: _strArrayJoin(
      src.color_palette !== undefined ? src.color_palette : src.palette,
      8000
    ),
    width: _num(widthRaw, 1024),
    height: _num(heightRaw, 1024),
    bgBrightness: _num(src.bgBrightness, 25),
    boxes,
  };
}

function _projectMethods(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const methodOrNull = (v) => (v == null ? null : _optStr(v, 200));
  const padOrNumber = (v, fallback) => {
    if (v == null) return fallback;
    if (typeof v === "boolean") return fallback;
    const n = typeof v === "string" && v.trim() !== "" ? Number(v) : v;
    return typeof n === "number" && Number.isFinite(n) ? n : fallback;
  };
  return {
    inpaintMethod: methodOrNull(src.inpaintMethod),
    inpaintOverride: _overridePair(src.inpaintOverride),
    expandMethod: methodOrNull(src.expandMethod),
    expandOverride: _overridePair(src.expandOverride),
    padTop: padOrNumber(src.padTop, 0),
    padRight: padOrNumber(src.padRight, 256),
    padBottom: padOrNumber(src.padBottom, 0),
    padLeft: padOrNumber(src.padLeft, 0),
  };
}

function _projectReferences(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const cards = [];
  if (Array.isArray(src.cards)) {
    for (const item of src.cards) {
      if (cards.length >= 64) break;
      if (!item || typeof item !== "object") continue;
      // Labels only, trimmed and non-empty (the backend requires a
      // non-empty label; whitespace-only labels are dropped, never stored).
      // Card files/ids are image pointers — never captured.
      const label = typeof item.label === "string" && !isImageLikeValue(item.label)
        ? item.label.trim().slice(0, PRESET_STRING_MAX)
        : "";
      if (!label) continue;
      cards.push({ label });
    }
  }
  return {
    method: _optStr(src.method != null ? src.method : src.referenceMethod, 200),
    override: _overridePair(src.override != null ? src.override : src.referenceOverride),
    cards,
  };
}

function _projectGuidance(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const cond = src.conditioning && typeof src.conditioning === "object" ? src.conditioning : {};
  const nodes = src.nodes && typeof src.nodes === "object" ? src.nodes : {};
  const controller = src.controller && typeof src.controller === "object" ? src.controller : {};
  const ctrlCheckpoint = controller.checkpoint != null
    ? controller.checkpoint
    : (typeof controller === "string" ? controller : src.controller_checkpoint);
  const numOr = (v, fallback) => {
    if (v == null) return fallback;
    if (typeof v === "boolean") return fallback;
    const n = typeof v === "string" && v.trim() !== "" ? Number(v) : v;
    return typeof n === "number" && Number.isFinite(n) ? n : fallback;
  };
  return {
    engaged: _bool(src.engaged, false),
    mode: _optStr(src.mode, 200),
    mechanism: _optStr(src.mechanism, 200),
    model_sha256: _sha256OrEmpty(src.model_sha256 != null ? src.model_sha256 : src.sha),
    mapping_revision: src.mapping_revision != null && src.mappingRevision == null
      ? _optStr(src.mapping_revision, 200)
      : _optStr(src.mappingRevision != null ? src.mappingRevision : src.mapping_revision, 200),
    controller: {
      checkpoint: _optStr(ctrlCheckpoint, 500),
      folder: _optStr(controller.folder, 500),
      checkpoint_sha256: _sha256OrEmpty(controller.checkpoint_sha256),
    },
    nodes: {
      loader: _optStr(nodes.loader, 200),
      apply: _optStr(nodes.apply, 200),
      preprocessor: _optStr(nodes.preprocessor, 200),
    },
    conditioning: {
      strength: numOr(cond.strength, 0.7),
      start: numOr(cond.start, 0),
      end: numOr(cond.end, 0.8),
    },
  };
}

function _projectSketch(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  return {
    tool: _optStr(src.tool, 80) || "brush",
    brushSize: _num(src.brushSize, 8),
    opacity: _num(src.opacity, 1),
    hardness: _num(src.hardness, 0.8),
    color: _optStr(src.color, 64),
    bgColor: _optStr(src.bgColor, 64),
    width: _num(src.width, 1024),
    height: _num(src.height, 1024),
  };
}

// Post recipe: the backend frozen set only (scalar-or-null values).
// Exposure/contrast/grain-style engine knobs are NOT allowlisted
// server-side — they are dropped here so saves never fail on them.
const PRESET_POST_RECIPE_FIELDS = Object.freeze([
  "curves",
  "mixer",
  "grading",
  "crop",
  "format",
  "quality",
  "embedMetadata",
  "embed_metadata",
]);

function _projectPostRecipe(recipe) {
  const src = recipe && typeof recipe === "object" ? recipe : {};
  const out = {};
  for (const key of PRESET_POST_RECIPE_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
    const value = src[key];
    if (value == null) {
      out[key] = null;
      continue;
    }
    if (typeof value === "string") {
      if (isImageLikeValue(value)) continue;
      out[key] = value.slice(0, PRESET_STRING_MAX);
    } else if (typeof value === "boolean") {
      out[key] = value;
    } else if (typeof value === "number" && Number.isFinite(value)) {
      out[key] = value;
    }
    // Lists/objects (spot lists, LUT contents, curve tables) are rejected
    // server-side — dropped here.
  }
  return out;
}

function _projectPost(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const recipe = src.recipe && typeof src.recipe === "object" ? src.recipe : {};
  return { recipe: _projectPostRecipe(recipe) };
}

/** Flat output shape (mirrors the backend section exactly). */
function _projectOutput(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const save = src.save && typeof src.save === "object" ? src.save : {};
  const preview = src.preview && typeof src.preview === "object" ? src.preview : {};
  const out = {};
  const format = src.format != null ? src.format : src.output_format;
  if (format !== undefined) {
    const f = _optStr(format, 40);
    if (f) out.output_format = f;
  }
  const quality = src.quality;
  if (quality !== undefined && quality !== null && typeof quality !== "boolean") {
    const n = typeof quality === "string" && quality.trim() !== "" ? Number(quality) : quality;
    if (typeof n === "number" && Number.isFinite(n)) out.quality = n;
  }
  // webp_lossless_compression is a backend bool; the frontend lane stores a
  // named string ("balanced"), which is unrepresentable — omitted (the
  // backend field is optional).
  const autoSave = src.auto_save_local !== undefined ? src.auto_save_local : save.auto_save_local;
  if (autoSave !== undefined) out.auto_save_local = _bool(autoSave, false);
  const folderRaw = src.save_folder !== undefined ? src.save_folder : save.save_folder;
  if (folderRaw !== undefined) out.save_folder = _optStr(folderRaw, 500);
  const sidecar = src.save_metadata_sidecar !== undefined
    ? src.save_metadata_sidecar
    : save.save_metadata_sidecar;
  if (sidecar !== undefined) out.save_metadata_sidecar = _bool(sidecar, true);
  const previewEntries = [
    ["preview_default", preview.preview_default !== undefined ? preview.preview_default : (src.preview_default !== undefined ? src.preview_default : src.data_saver_default)],
    ["preview_codec", preview.preview_codec !== undefined ? preview.preview_codec : (src.preview_codec !== undefined ? src.preview_codec : src.data_saver_codec)],
    ["preview_quality", preview.preview_quality !== undefined ? preview.preview_quality : (src.preview_quality !== undefined ? src.preview_quality : src.data_saver_quality)],
  ];
  for (const [key, value] of previewEntries) {
    if (value === undefined) continue;
    if (typeof value === "string") {
      const s = _optStr(value, 40);
      if (s) out[key] = s;
    } else if (typeof value === "boolean") {
      out[key] = value;
    } else if (typeof value === "number" && Number.isFinite(value)) {
      out[key] = value;
    }
  }
  return out;
}

const SECTION_PROJECTORS = {
  core: _projectCore,
  styles: _projectStyles,
  layout: _projectLayout,
  methods: _projectMethods,
  references: _projectReferences,
  guidance: _projectGuidance,
  sketch: _projectSketch,
  post: _projectPost,
  output: _projectOutput,
};

/**
 * Capture a detached v1 preset state from owner-native snapshots.
 * Explicit allowlist projection per section — never clone-then-delete, so
 * image-bearing fields cannot leak through. ALWAYS emits all nine sections
 * (neutral for absent owners) because the backend requires every section.
 */
export function capturePresetState(ownerSnapshots) {
  const src = ownerSnapshots && typeof ownerSnapshots === "object" ? ownerSnapshots : {};
  const state = { schema_version: PRESET_SCHEMA_VERSION };
  for (const section of PRESET_SECTIONS) {
    const input = Object.prototype.hasOwnProperty.call(src, section) ? src[section] : {};
    state[section] = SECTION_PROJECTORS[section](input == null ? {} : input);
  }
  return state;
}

/** Approximate JSON byte size of a state object. */
export function presetStateByteSize(state) {
  try {
    return new Blob([JSON.stringify(state)]).size;
  } catch (_e) {
    try {
      return String(JSON.stringify(state)).length;
    } catch (_e2) {
      return Infinity;
    }
  }
}

// ── Validation (client pre-check; the server stays the authority) ─────────

function _scanImageLeakage(value, path, hits) {
  if (typeof value === "string") {
    if (isBackendImageValue(value)) hits.push(path);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, i) => _scanImageLeakage(item, path + "[" + i + "]", hits));
    return;
  }
  if (value && typeof value === "object") {
    for (const key of Object.keys(value)) {
      if (isImageKey(key)) {
        hits.push(path ? path + "." + key : key);
        continue;
      }
      _scanImageLeakage(value[key], path ? path + "." + key : key, hits);
    }
  }
}

/**
 * Shape-validate a v1 preset state. Returns {ok, issues[]} where each issue
 * is {section, code, message, blocking}. Blocking issues must stop a load;
 * the loader never auto-runs and never silently substitutes.
 * Absent studio_state (legacy/compat records) is NOT an error here — it
 * yields ok:true with zero sections (callers treat it as "nothing to
 * hydrate"). Use planPresetHydration for load-time blocking semantics.
 */
export function validatePresetState(state) {
  const issues = [];
  const block = (section, code, message) => issues.push({ section, code, message, blocking: true });
  if (state == null) return { ok: true, issues, legacy: true };
  if (typeof state !== "object" || Array.isArray(state)) {
    block("", "not_an_object", "Saved workflow state must be an object.");
    return { ok: false, issues };
  }
  if (typeof state.schema_version !== "number" || state.schema_version !== PRESET_SCHEMA_VERSION) {
    block("", "schema_mismatch", "Unsupported saved workflow schema_version (expected 1).");
    return { ok: false, issues };
  }
  for (const key of Object.keys(state)) {
    if (key === "schema_version") continue;
    if (PRESET_SECTIONS.indexOf(key) === -1) {
      block(key, "unknown_section", "Unknown saved workflow section '" + key + "'.");
    }
  }
  // The backend requires every section — flag absent ones (load plans them
  // to neutral and reports; saves always emit all sections).
  for (const section of PRESET_SECTIONS) {
    if (!Object.prototype.hasOwnProperty.call(state, section)) {
      block(section, "missing_section", "Saved workflow section '" + section + "' is required.");
    } else if (state[section] == null || typeof state[section] !== "object" || Array.isArray(state[section])) {
      block(section, "section_shape", "Saved workflow section '" + section + "' must be an object.");
    }
  }
  // Scan within each section (never the root): section names themselves are
  // legitimate contract words.
  const leaks = [];
  for (const key of Object.keys(state)) {
    if (key === "schema_version") continue;
    if (PRESET_SECTIONS.indexOf(key) === -1) continue;
    _scanImageLeakage(state[key], key, leaks);
  }
  for (const hit of leaks) {
    block(hit.split(".")[0] || "", "image_key", "Image-bearing field '" + hit + "' must not be in a saved workflow.");
  }
  // Null control values are rejected server-side — catch them early.
  try {
    const controls = state.core && state.core.controls;
    if (controls && typeof controls === "object") {
      for (const role of Object.keys(controls)) {
        const value = controls[role];
        if (value == null || (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean")) {
          block("core", "control_scalar", "Control '" + role + "' must be a string, number, or boolean scalar.");
          break;
        }
      }
    }
  } catch (_e) {}
  let size = 0;
  try {
    size = presetStateByteSize(state);
  } catch (_e2) {
    size = Infinity;
  }
  if (size > PRESET_STATE_MAX_BYTES) {
    block("", "too_large", "Saved workflow state exceeds the 64KiB cap.");
  }
  return { ok: issues.length === 0, issues };
}

// ── Hydration planning ────────────────────────────────────────────────────

function _issue(section, code, message, blocking) {
  return { section, code, message, blocking: blocking === true };
}

/** Neutral (reset) value per section — hydration target when omitted. */
export function neutralPresetSection(section) {
  switch (section) {
    case "core":
      return {
        positive_prompt: "",
        negative_prompt: "",
        controls: {},
        activeMode: "",
        activeSubtool: "",
        skipTextGenerate: false,
      };
    case "styles":
      return { setId: "", selectedId: "", basePrompt: "" };
    case "layout":
      return {
        high_level_description: "",
        background: "",
        style_mode: "none",
        aesthetics: "",
        lighting: "",
        photo: "",
        medium: "",
        art_style: "",
        color_palette: "",
        width: 1024,
        height: 1024,
        bgBrightness: 25,
        boxes: [],
      };
    case "methods":
      return {
        inpaintMethod: null,
        inpaintOverride: null,
        expandMethod: null,
        expandOverride: null,
        padTop: 0,
        padRight: 256,
        padBottom: 0,
        padLeft: 0,
      };
    case "references":
      return { method: "", override: null, cards: [] };
    case "guidance":
      return {
        engaged: false,
        mode: "",
        mechanism: "",
        model_sha256: "",
        mapping_revision: "",
        controller: {},
        nodes: {},
        conditioning: {},
      };
    case "sketch":
      return {
        tool: "brush",
        brushSize: 8,
        opacity: 1,
        hardness: 0.8,
        color: "",
        bgColor: "",
        width: 1024,
        height: 1024,
      };
    case "post":
      return { recipe: {} };
    case "output":
      return {};
    default:
      return null;
  }
}

/**
 * Plan hydration of a validated v1 state against the live target context.
 * Double-projects through the section allowlists so image-bearing fields
 * can never survive even if validation was bypassed. Omitted sections plan
 * to neutral (never inherit live values).
 *
 * targetContext (all optional, plain data only):
 *   workflowVersionId, boundReferenceMethod, referenceSlotCount,
 *   guidanceMapping: null | {record, stale?, staleDetail?},
 *   styleSetIds: string[], styleIds: string[]
 *
 * (Inpaint/expand methods are free per-workflow choices with no version
 * binding, so they restore as-is; only references/mappings/styles/guidance
 * revalidate against live bindings.)
 *
 * Returns {sections: {name: {present, value}}, issues[]}. Blocking issues
 * (blocking:true) must stop the load fail-closed with a bounded per-feature
 * warning; non-blocking issues are stale-shape notices that preserve the
 * rest.
 */
export function planPresetHydration(state, targetContext) {
  const ctx = targetContext && typeof targetContext === "object" ? targetContext : {};
  const issues = [];
  const sections = {};

  const validation = validatePresetState(state);
  for (const issue of validation.issues) issues.push(issue);
  const blockingValidation = validation.issues.some((i) => i.blocking);
  const src = state && typeof state === "object" && !Array.isArray(state) ? state : null;

  const planSection = (name, check) => {
    if (!src || !Object.prototype.hasOwnProperty.call(src, name) || src[name] == null) {
      sections[name] = { present: false, value: neutralPresetSection(name) };
      return;
    }
    // Double-projection: re-run the allowlist over the stored section.
    const value = SECTION_PROJECTORS[name](src[name]);
    const result = check ? check(value) : { value, issues: [] };
    sections[name] = { present: true, value: result.value };
    for (const issue of result.issues || []) issues.push(issue);
  };

  if (blockingValidation) {
    // Fail closed: nothing hydrates, every present section plans to neutral.
    for (const name of PRESET_SECTIONS) {
      sections[name] = {
        present: !!(src && Object.prototype.hasOwnProperty.call(src, name)),
        value: neutralPresetSection(name),
      };
    }
    return { sections, issues };
  }

  planSection("core", null);
  planSection("styles", (value) => {
    const local = [];
    const styleIds = Array.isArray(ctx.styleIds) ? ctx.styleIds : null;
    if (value.selectedId) {
      const known = styleIds ? styleIds.indexOf(value.selectedId) !== -1 : true;
      if (!known) {
        local.push(
          _issue("styles", "stale_style", "Style '" + value.selectedId + "' is not in the catalog — style left unset, rest preserved.", false)
        );
        value = Object.assign({}, value, { selectedId: "", setId: "" });
      } else if (Array.isArray(ctx.styleSetIds) && value.setId && ctx.styleSetIds.indexOf(value.setId) === -1) {
        value = Object.assign({}, value, { setId: "" });
      }
    }
    return { value, issues: local };
  });
  planSection("layout", null);
  planSection("methods", (value) => {
    // Free per-workflow choices: restore as-is (no version binding exists
    // for inpaint/expand). Only the pair shape is enforced by projection.
    return { value, issues: [] };
  });
  planSection("references", (value) => {
    const local = [];
    if (value.method && ctx.boundReferenceMethod) {
      if (value.method !== ctx.boundReferenceMethod) {
        local.push(
          _issue("references", "stale_reference_method", "Reference method '" + value.method + "' is not bound in this workflow version (bound: '" + ctx.boundReferenceMethod + "'). References left unset.", false)
        );
        return { value: neutralPresetSection("references"), issues: local };
      }
      if (
        value.method === "conditioning_slots" &&
        typeof ctx.referenceSlotCount === "number" &&
        value.cards.length > ctx.referenceSlotCount
      ) {
        local.push(
          _issue("references", "reference_over_capacity", "This version exposes " + ctx.referenceSlotCount + " reference slots — excess reference labels dropped.", false)
        );
        value = Object.assign({}, value, { cards: value.cards.slice(0, ctx.referenceSlotCount) });
      }
    } else if (value.method && ctx.boundReferenceMethod === "") {
      // Unbound version (no reference bindings at all): unlike a STALE method
      // mismatch (fail-closed above), there is nothing to conflict with — the
      // backend contract keeps method + label order with no binding membership
      // check (studio_domain/preset_state.py _norm_references: cards carry only
      // {label}, order preserved; images are never stored). Silently dropping
      // the labels would lose user data, so restore the labeled EMPTY cards
      // (fresh runtime ids + empty files happen at apply time) with a bounded
      // warning; images are still picked explicitly after load.
      local.push(
        _issue("references", "reference_unbound", "This workflow version has no reference bindings — reference labels restored without images; pick images explicitly.", false)
      );
      return { value, issues: local };
    }
    return { value, issues: local };
  });
  planSection("guidance", (value) => {
    const local = [];
    if (value.engaged !== true) return { value, issues: local };
    // Guidance hydration NEVER substitutes mappings and never calls
    // mapping-save/confirm APIs (this module has no such imports by
    // construction). Missing/stale -> the requested mode stays restored and
    // the normal Phase-9 check (resolveGuidanceState) shows its blocked/
    // manual state ("Guidance unavailable ... Choose mapping") with the run
    // gate engaged — fail-closed means no silent unguided run, never a silent
    // reset to Off (which would drop the requested mode and its gate).
    const mapping = ctx.guidanceMapping != null ? ctx.guidanceMapping : null;
    if (!mapping || !mapping.record) {
      local.push(
        _issue("guidance", "guidance_mapping_missing", "Guidance is engaged in the saved workflow but this model has no confirmed mapping — requested mode restored, run stays blocked. Confirm a mapping manually to re-engage.", true)
      );
      return { value, issues: local };
    }
    if (mapping.stale === true) {
      local.push(
        _issue("guidance", "guidance_mapping_stale", "Guidance mapping changed since the saved workflow was saved (" + String(mapping.staleDetail || "dependency changed") + ") — requested mode restored, run stays blocked. Review and reconfirm manually.", true)
      );
      return { value, issues: local };
    }
    return { value, issues: local };
  });
  planSection("sketch", null);
  planSection("post", null);
  planSection("output", null);

  return { sections, issues };
}

/**
 * Storage key for the image-free working draft: exact version + preset id.
 * Reload restores only the matching-revision draft.
 */
export function presetDraftKey(workflowVersionId, presetId) {
  return String(workflowVersionId || "") + "::" + String(presetId || "");
}

const PRESET_MAX_TAGS = 20;
const PRESET_MAX_TAG_LEN = 80;
const PRESET_MAX_NAME_LEN = 200;
const PRESET_MAX_DESC_LEN = 2000;

/**
 * Pure: save-payload builder for POST /versions/{vid}/presets. Name is
 * required ( backend: stripped, 1..200 chars); description ≤ 2000; tags are
 * trimmed, deduped, ≤ 20 entries of ≤ 80 chars (mirrors the backend
 * metadata validator; the server stays the authority). Images are never
 * part of the payload (note callers surface: "Images are not saved with
 * workflows."). Returns {ok, payload} or {ok:false, error}.
 */
export function buildPresetSavePayload(input) {
  const src = input && typeof input === "object" ? input : {};
  const name = String(src.name == null ? "" : src.name).trim();
  if (!name) return { ok: false, error: "Name is required." };
  if (name.length > PRESET_MAX_NAME_LEN) {
    return { ok: false, error: "Name exceeds 200 characters." };
  }
  const description = src.description == null ? "" : String(src.description);
  if (description.length > PRESET_MAX_DESC_LEN) {
    return { ok: false, error: "Description exceeds 2000 characters." };
  }
  const state = src.studio_state && typeof src.studio_state === "object" ? src.studio_state : null;
  if (!state) return { ok: false, error: "Saved workflow state is required." };
  const validation = validatePresetState(state);
  if (!validation.ok) {
    return { ok: false, error: (validation.issues[0] && validation.issues[0].message) || "Invalid saved workflow state." };
  }
  if (presetStateByteSize(state) > PRESET_STATE_MAX_BYTES) {
    return { ok: false, error: "Saved workflow state exceeds the 64KiB cap." };
  }
  const tags = [];
  if (Array.isArray(src.tags)) {
    for (const tag of src.tags) {
      if (tags.length >= PRESET_MAX_TAGS) break;
      if (typeof tag !== "string") continue;
      const trimmed = tag.trim();
      if (!trimmed || tags.indexOf(trimmed) !== -1) continue;
      tags.push(trimmed.slice(0, PRESET_MAX_TAG_LEN));
    }
  }
  return {
    ok: true,
    payload: {
      name,
      description,
      tags,
      studio_state: state,
    },
  };
}

/**
 * Deterministic style composition for preset style loads: restores the base
 * prompt, composes once with the catalog fragment. Pure (the catalog lookup
 * stays with the caller so this module never touches the DOM/store).
 */
export function composePresetStylePrompt(basePrompt, fragment) {
  const user = String(basePrompt == null ? "" : basePrompt).trim();
  const frag = String(fragment == null ? "" : fragment).trim();
  if (!frag) return String(basePrompt == null ? "" : basePrompt);
  if (!user) return frag;
  return user + ", " + frag;
}
