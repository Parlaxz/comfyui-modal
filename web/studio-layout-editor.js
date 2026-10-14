/**
 * Studio-native Ideogram4 layout editor (KJNodes Ideogram4 port).
 *
 * Portions adapted from ComfyUI-KJNodes
 * Copyright (C) Kijai
 * Source: https://github.com/kijai/ComfyUI-KJNodes
 * Commit: d7641533d6634eb05f8570c980fce8fc8528dc7b
 * Modified by comfyui-modal on 2026-10-14
 * Licensed GPL-3.0-or-later.
 *
 * Studio adaptation notes (what was stripped / changed):
 * - No ComfyUI node-shell chrome, no LiteGraph deps, no ComfyUI widgets/inputs.
 * - No References/Guidance/Sketch/Upscale/Presets/graph framework (out of scope).
 * - bbox coordinate space is fixed to the Ideogram default: coord_mode normalized
 *   (0-1000 grid) + bbox_order yx ([ymin,xmin,ymax,xmax]). The upstream toolbar
 *   absolute-pixels / xy-order toggles are intentionally omitted.
 * - Background image is a local file upload only. The upstream Live sampling
 *   preview / Grab BG / Clear BG controls (~2490-2585) depend on ComfyUI
 *   execution events and are omitted.
 * - Templates persist via localStorage only. The upstream server-side userdata
 *   templates (TPL_DIR kjnodes/ideogram4/templates, upstream lines 71-97)
 *   require the ComfyUI userdata API and are omitted.
 * - Composition guides / grid-snap toolbar are omitted (not in the Studio seam).
 */

const HANDLE = 8; // hit radius (canvas px) for resize handles (upstream HANDLE)
const MAX_ELEM_COLORS = 5; // Ideogram 4 per-element palette cap (upstream)
const MAX_STYLE_COLORS = 16; // Ideogram 4 style palette cap (upstream)
const LS_LAYOUT_LEGACY = "comfymodal.studio.layout.v1"; // legacy draft store (percent units)
const LS_LAYOUT_KJ = "comfymodal.studio.layout.kj.v1"; // Studio KJ draft store (fraction units)
const LS_TEMPLATES = "comfymodal.studio.layout.templates.v1"; // localStorage templates (see header)
const DIM_MIN = 64;
const DIM_STEP = 16;
const DEFAULT_DIM = 1024;
const DEFAULT_BRIGHTNESS = 25; // hidden bg-brightness field default (upstream bg_brightness default 25)

let copiedBoxes = null; // internal region clipboard (upstream: module-level copiedBoxes)
let uidCounter = 0;
function uid() {
  uidCounter += 1;
  return "box-" + Date.now().toString(36) + "-" + uidCounter.toString(36);
}

function clamp01(v) {
  const n = Number(v);
  if (!isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function paletteUpper(colors) {
  // Port of upstream python _palette (ideogram4_nodes.py): ordered, empties dropped, uppercased.
  if (!colors) return [];
  const list = Array.isArray(colors) ? colors : Object.values(colors);
  const out = [];
  for (const c of list) {
    if (typeof c === "string" && c.trim()) out.push(c.trim().toUpperCase());
  }
  return out;
}

/**
 * {x,y,w,h} fractions (0-1) -> [ymin,xmin,ymax,xmax] on the 0-1000 grid.
 * Port of upstream python _norm_bbox (ideogram4_nodes.py lines 133-151) with the
 * Ideogram defaults sx=sy=1000, order="yx": clamp each extent, sort reversed
 * extents, round to ints.
 */
export function normBboxToGrid(box) {
  const b = box || {};
  const x = Number(b.x) || 0;
  const y = Number(b.y) || 0;
  const w = Number(b.w) || 0;
  const h = Number(b.h) || 0;
  const cx = (v) => Math.max(0, Math.min(1000, Math.round(v * 1000)));
  const cy = (v) => Math.max(0, Math.min(1000, Math.round(v * 1000)));
  let ymin = cy(y);
  let xmin = cx(x);
  let ymax = cy(y + h);
  let xmax = cx(x + w);
  if (ymin > ymax) {
    const t = ymin;
    ymin = ymax;
    ymax = t;
  }
  if (xmin > xmax) {
    const t = xmin;
    xmin = xmax;
    xmax = t;
  }
  return [ymin, xmin, ymax, xmax];
}

/** Normalize a fractional box in place: flip negative extents, clamp to 0-1. */
function normalizeBox(b) {
  let x = Number(b.x) || 0;
  let y = Number(b.y) || 0;
  let w = Number(b.w) || 0;
  let h = Number(b.h) || 0;
  if (w < 0) {
    x += w;
    w = -w;
  }
  if (h < 0) {
    y += h;
    h = -h;
  }
  x = clamp01(x);
  y = clamp01(y);
  w = Math.max(0, Math.min(1 - x, w));
  h = Math.max(0, Math.min(1 - y, h));
  b.x = x;
  b.y = y;
  b.w = w;
  b.h = h;
  return b;
}

function blankDraft() {
  return {
    boxes: [],
    high_level_description: "",
    background: "",
    style_mode: "none",
    aesthetics: "",
    lighting: "",
    photo: "",
    medium: "",
    art_style: "",
    color_palette: [],
    width: DEFAULT_DIM,
    height: DEFAULT_DIM,
    bgBrightness: DEFAULT_BRIGHTNESS,
  };
}

function snapDim(v) {
  let n = Math.round((Number(v) || DEFAULT_DIM) / DIM_STEP) * DIM_STEP;
  if (!isFinite(n)) n = DEFAULT_DIM;
  return Math.max(DIM_MIN, n);
}

function normalizeDraft(raw) {
  const d = Object.assign(blankDraft(), raw || {});
  d.boxes = Array.isArray(d.boxes) ? d.boxes : [];
  d.boxes = d.boxes.filter((b) => b && typeof b === "object").map((b) => {
    const rawType = b.type != null ? b.type : b.kind;
    const nb = {
      id: typeof b.id === "string" && b.id ? b.id : uid(),
      type: rawType === "text" ? "text" : "obj",
      x: Number(b.x) || 0,
      y: Number(b.y) || 0,
      w: Number(b.w) || 0,
      h: Number(b.h) || 0,
      desc: b.desc != null ? String(b.desc) : (b.label != null ? String(b.label) : ""),
      text: b.text != null ? String(b.text) : "",
      color_palette: paletteUpper(b.color_palette != null ? b.color_palette : (b.color ? [b.color] : [])).slice(0, MAX_ELEM_COLORS),
      nobbox: !!b.nobbox,
      locked: !!b.locked,
    };
    return normalizeBox(nb);
  });
  d.style_mode = d.style_mode === "photo" || d.style_mode === "art_style" ? d.style_mode : "none";
  d.color_palette = paletteUpper(d.color_palette).slice(0, MAX_STYLE_COLORS);
  for (const k of ["high_level_description", "background", "aesthetics", "lighting", "photo", "medium", "art_style"]) {
    d[k] = d[k] != null ? String(d[k]) : "";
  }
  d.width = snapDim(d.width);
  d.height = snapDim(d.height);
  d.bgBrightness = Math.max(0, Math.min(100, Math.round(Number(d.bgBrightness != null ? d.bgBrightness : DEFAULT_BRIGHTNESS))));
  if (!isFinite(d.bgBrightness)) d.bgBrightness = DEFAULT_BRIGHTNESS;
  return d;
}

/**
 * Build the Ideogram 4 structured caption from a Studio draft.
 * Port of upstream python execute caption assembly (ideogram4_nodes.py lines 330-445):
 * high_level_description omitted when blank; style block emitted only when a style
 * mode is chosen (every style key present, blanks kept, key order preserved);
 * elements carry type first, bbox omitted for unplaced (nobbox) elements, text only
 * for text elements, desc always emitted, per-element palette uppercased max 5.
 * bbox uses the Ideogram defaults (normalized 0-1000 grid, yx order).
 */
export function buildIdeogramCaption(draft) {
  const d = draft || {};
  const boxes = Array.isArray(d.boxes) ? d.boxes : [];
  const caption = {};
  const hld = d.high_level_description != null ? String(d.high_level_description) : "";
  if (hld.trim()) caption.high_level_description = hld;

  const mode = d.style_mode || "none";
  if (mode !== "none") {
    const sd = {
      aesthetics: d.aesthetics != null ? String(d.aesthetics) : "",
      lighting: d.lighting != null ? String(d.lighting) : "",
    };
    if (mode === "photo") {
      sd.photo = d.photo != null ? String(d.photo) : "";
      sd.medium = d.medium != null ? String(d.medium) : "";
    } else {
      sd.medium = d.medium != null ? String(d.medium) : "";
      sd.art_style = d.art_style != null ? String(d.art_style) : "";
    }
    const pal = paletteUpper(d.color_palette).slice(0, MAX_STYLE_COLORS);
    if (pal.length) sd.color_palette = pal;
    caption.style_description = sd;
  }

  const elements = [];
  for (const b of boxes) {
    if (!b || typeof b !== "object") continue;
    const rawType = b.type != null ? b.type : b.kind;
    const etype = rawType === "text" ? "text" : "obj";
    const elem = { type: etype }; // key order matters (upstream)
    if (!b.nobbox) elem.bbox = normBboxToGrid(b); // upstream normBboxJS 2071-2076 / captionBboxJS 2078-2088
    if (etype === "text") elem.text = b.text != null ? String(b.text) : "";
    elem.desc = b.desc != null ? String(b.desc) : (b.label != null ? String(b.label) : "");
    const pal = paletteUpper(b.color_palette != null ? b.color_palette : (b.color ? [b.color] : [])).slice(0, MAX_ELEM_COLORS);
    if (pal.length) elem.color_palette = pal;
    elements.push(elem);
  }
  caption.compositional_deconstruction = {
    background: d.background != null ? String(d.background) : "",
    elements,
  };
  return { json: caption, text: JSON.stringify(caption) };
}

function repairJsonString(s) {
  // Port of upstream python _repair_json (ideogram4_nodes.py lines 180-207):
  // slice the outermost {...}, strip trailing commas before } or ].
  const i = s.indexOf("{");
  const j = s.lastIndexOf("}");
  const t = (i !== -1 && j > i) ? s.slice(i, j + 1) : s;
  return t.replace(/("(?:[^"\\]|\\.)*")|,(\s*[}\]])/g, (m, str, tail) => str || tail);
}

function parseCaptionString(s) {
  // Port of upstream python _loads_caption (ideogram4_nodes.py): strict parse,
  // then one lenient-repair retry. Returns the dict or null.
  if (!s || !String(s).trim()) return null;
  const str = String(s);
  const cands = [str, repairJsonString(str)];
  for (const cand of cands) {
    try {
      const v = JSON.parse(cand);
      if (v && typeof v === "object" && !Array.isArray(v)) return v;
    } catch (e) { /* try next candidate */ }
  }
  return null;
}

/**
 * Caption dict (or JSON string) -> Studio draft.
 * Port of upstream python _caption_to_boxes (ideogram4_nodes.py lines 209-229):
 * bbox [ymin,xmin,ymax,xmax] / 1000 -> fractions; elements without a bbox become
 * unplaced (nobbox) placeholders.
 */
export function parseIdeogramCaption(obj) {
  const cap = typeof obj === "string" ? parseCaptionString(obj) : obj;
  if (!cap || typeof cap !== "object" || Array.isArray(cap)) return blankDraft();
  const cd = (cap.compositional_deconstruction && typeof cap.compositional_deconstruction === "object")
    ? cap.compositional_deconstruction : {};
  const sd = (cap.style_description && typeof cap.style_description === "object") ? cap.style_description : null;
  const draft = blankDraft();
  draft.high_level_description = cap.high_level_description != null ? String(cap.high_level_description) : "";
  draft.background = cd.background != null ? String(cd.background) : "";
  if (sd) {
    draft.aesthetics = sd.aesthetics != null ? String(sd.aesthetics) : "";
    draft.lighting = sd.lighting != null ? String(sd.lighting) : "";
    if ("photo" in sd) {
      draft.style_mode = "photo";
      draft.photo = sd.photo != null ? String(sd.photo) : "";
      draft.medium = sd.medium != null ? String(sd.medium) : "";
    } else if ("art_style" in sd) {
      draft.style_mode = "art_style";
      draft.medium = sd.medium != null ? String(sd.medium) : "";
      draft.art_style = sd.art_style != null ? String(sd.art_style) : "";
    } else {
      draft.style_mode = "photo";
      draft.medium = sd.medium != null ? String(sd.medium) : "";
    }
    draft.color_palette = paletteUpper(sd.color_palette || []).slice(0, MAX_STYLE_COLORS);
  }
  const els = Array.isArray(cd.elements) ? cd.elements : [];
  for (const el of els) {
    if (!el || typeof el !== "object") continue;
    const box = {
      id: uid(),
      type: el.type === "text" ? "text" : "obj",
      text: el.text != null ? String(el.text) : "",
      desc: el.desc != null ? String(el.desc) : "",
      color_palette: paletteUpper(el.color_palette || []).slice(0, MAX_ELEM_COLORS),
      locked: false,
      nobbox: false,
      x: 0.03, y: 0.03, w: 0.22, h: 0.14,
    };
    const bb = el.bbox;
    if (Array.isArray(bb) && bb.length === 4 && bb.every((v) => isFinite(Number(v)))) {
      const nums = bb.map(Number);
      const ymin = nums[0]; const xmin = nums[1]; const ymax = nums[2]; const xmax = nums[3];
      box.x = clamp01(Math.min(xmin, xmax) / 1000);
      box.y = clamp01(Math.min(ymin, ymax) / 1000);
      box.w = clamp01(Math.abs(xmax - xmin) / 1000);
      box.h = clamp01(Math.abs(ymax - ymin) / 1000);
      normalizeBox(box);
    } else {
      box.nobbox = true; // no bbox: unplaced placeholder (upstream)
    }
    draft.boxes.push(box);
  }
  return draft;
}

/** Migrate a raw persisted object to fraction-unit canonical draft (legacy percent -> fraction). */
function migratePersistedDraft(raw) {
  if (!raw || typeof raw !== "object") return null;
  const d = Object.assign({}, raw);
  if (Array.isArray(d.boxes)) {
    d.boxes = d.boxes.map((b) => {
      if (!b || typeof b !== "object") return b;
      const nb = Object.assign({}, b);
      // Legacy percent store: any extent with |v| > 1 is percent -> fraction.
      for (const k of ["x", "y", "w", "h"]) {
        const v = Number(nb[k]);
        if (isFinite(v) && Math.abs(v) > 1) nb[k] = v / 100;
      }
      if (nb.kind != null && nb.type == null) nb.type = nb.kind;
      if (nb.label != null && nb.desc == null) nb.desc = nb.label;
      if (nb.color != null && nb.color_palette == null) nb.color_palette = [nb.color];
      return nb;
    });
  }
  return normalizeDraft(d);
}

function loadPersistedDraft() {
  // LOAD: prefer the new fraction store, fall back to the legacy percent store.
  try {
    const kj = window.localStorage.getItem(LS_LAYOUT_KJ);
    if (kj) {
      const d = migratePersistedDraft(JSON.parse(kj));
      if (d) return d;
    }
  } catch (e) { /* corrupted store -> ignore */ }
  try {
    const legacy = window.localStorage.getItem(LS_LAYOUT_LEGACY);
    if (legacy) {
      const d = migratePersistedDraft(JSON.parse(legacy));
      if (d) return d;
    }
  } catch (e) { /* corrupted store -> ignore */ }
  return null;
}

function persistDraft(draft) {
  // SAVE: always write the new fraction-unit key (legacy key is read-only fallback).
  try {
    window.localStorage.setItem(LS_LAYOUT_KJ, JSON.stringify(draft));
  } catch (e) { /* private mode / quota -> editing still works in memory */ }
}

// Parse a clipboard/string color into normalized #rrggbb (upstream parseColorString).
function parseColorString(s) {
  if (!s) return null;
  const t = String(s).trim();
  let m = t.match(/^#?([0-9a-fA-F]{6})$/);
  if (m) return "#" + m[1].toLowerCase();
  m = t.match(/^#?([0-9a-fA-F]{3})$/);
  if (m) {
    const h = m[1];
    return ("#" + h[0] + h[0] + h[1] + h[1] + h[2] + h[2]).toLowerCase();
  }
  m = t.match(/^rgba?\(\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)/i);
  if (m) {
    const h2 = (n) => Math.max(0, Math.min(255, parseInt(n, 10))).toString(16).padStart(2, "0");
    return "#" + h2(m[1]) + h2(m[2]) + h2(m[3]);
  }
  return null;
}

let styleInjected = false;
function injectStyle() {
  if (styleInjected || typeof document === "undefined") return;
  if (document.getElementById("studio-layout-style")) {
    styleInjected = true;
    return;
  }
  styleInjected = true;
  const s = document.createElement("style");
  s.id = "studio-layout-style";
  s.textContent = [
    ".stlay-wrap{display:flex;flex-direction:column;gap:8px;font:12px sans-serif;color:#ccc;}",
    ".stlay-bar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;}",
    ".stlay-btn{background:#333;border:1px solid #555;border-radius:4px;color:#bbb;font:11px sans-serif;cursor:pointer;padding:2px 8px;line-height:18px;white-space:nowrap;}",
    ".stlay-btn:hover{border-color:#46b4e6;color:#fff;}",
    ".stlay-field{background:#1d1d1d;border:1px solid #444;border-radius:4px;color:#ddd;font:12px sans-serif;padding:3px 6px;}",
    ".stlay-field:focus{border-color:#46b4e6;outline:none;}",
    ".stlay-area{width:100%;box-sizing:border-box;background:#1d1d1d;border:1px solid #444;border-radius:4px;color:#ddd;font:12px sans-serif;padding:4px 6px;resize:vertical;min-height:34px;}",
    ".stlay-cv{display:flex;align-items:center;justify-content:center;overflow:hidden;background:#111;border-radius:4px;min-height:120px;}",
    ".stlay-canvas{cursor:crosshair;display:block;background:#1a1a1a;border-radius:4px;outline:none;touch-action:none;}",
    ".stlay-main{display:flex;gap:8px;align-items:stretch;flex-wrap:wrap;}",
    ".stlay-side{flex:1 1 240px;min-width:220px;display:flex;flex-direction:column;gap:6px;max-height:520px;overflow-y:auto;background:#1e1e1e;border:1px solid #333;border-radius:4px;padding:6px;}",
    ".stlay-lrow{display:flex;align-items:center;gap:6px;padding:3px 5px;border-radius:4px;cursor:pointer;user-select:none;}",
    ".stlay-lrow:hover{background:#333;}",
    ".stlay-lrow.active{background:#2a3a42;box-shadow:inset 0 0 0 1px #46b4e6;}",
    ".stlay-list{max-height:190px;overflow-y:auto;}",
    ".stlay-lsw{width:16px;height:16px;border-radius:3px;border:1px solid #666;flex:0 0 auto;}",
    ".stlay-lnum{font:bold 11px monospace;color:#888;flex:0 0 auto;width:20px;}",
    ".stlay-ltext{flex:1 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}",
    ".stlay-ltext.empty{color:#777;font-style:italic;}",
    ".stlay-lbtn{background:none;border:none;color:#999;cursor:pointer;font:13px sans-serif;line-height:1;padding:2px 5px;border-radius:3px;flex:0 0 auto;}",
    ".stlay-lbtn:hover{color:#fff;background:#444;}",
    ".stlay-lbtn:disabled{opacity:0.3;cursor:default;}",
    ".stlay-lbtn:disabled:hover{color:#999;background:none;}",
    ".stlay-lbtn.del:hover{color:#fff;background:#a33;}",
    ".stlay-lbtn.on{background:#3a3320;}",
    ".stlay-sw{width:20px;height:20px;border:1px solid #666;border-radius:3px;cursor:pointer;flex-shrink:0;position:relative;touch-action:none;}",
    ".stlay-sw:hover{box-shadow:0 0 0 2px #46b4e6;z-index:3;}",
    ".stlay-sw input{position:absolute;opacity:0;width:0;height:0;pointer-events:none;}",
    ".stlay-lbl{color:#888;font-size:11px;}",
    ".stlay-pre{background:#141414;border:1px solid #333;border-radius:4px;color:#9dca9d;font:11px monospace;padding:6px;max-height:220px;overflow:auto;white-space:pre-wrap;word-break:break-word;}",
    ".stlay-inline{position:absolute;box-sizing:border-box;background:rgba(18,18,18,0.95);border:2px solid #46b4e6;border-radius:3px;color:#fff;font:12px monospace;padding:3px 4px;resize:none;outline:none;z-index:10;}",
    ".stlay-grid2{display:grid;grid-template-columns:repeat(4,minmax(52px,1fr));gap:4px;}",
    ".stlay-scene{background:#1c1c1e;border:1px solid #333;border-radius:6px;padding:8px;display:flex;flex-direction:column;gap:6px;}",
    ".stlay-sect{color:#aaa;font:bold 11px sans-serif;letter-spacing:0.04em;text-transform:uppercase;}",
    ".stlay-cv{flex:3 1 460px;}",
    ".stlay-canvas{width:100%;height:auto;box-shadow:0 0 0 1px #2c2c2c;}",
    ".stlay-side{flex:1 1 260px;max-width:360px;}",
    ".stlay-lrow .stlay-lnum{color:#aaa;}",
    ".stlay-disc{border:1px solid #333;border-radius:4px;padding:2px 6px 4px;background:#1a1a1c;}",
    ".stlay-disc>summary{cursor:pointer;color:#9db8c6;font-size:11px;padding:2px 0;}",
    ".stlay-disc>summary:hover{color:#fff;}",
    ".stlay-geosum{color:#8a8a8a;font-size:11px;}",
    ".stlay-util{display:flex;flex-direction:column;gap:6px;}",
  ].join("\n");
  document.head.appendChild(s);
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function cloneDraft(d) {
  return JSON.parse(JSON.stringify(d));
}

/**
 * Studio layout editor: canvas bbox editing + globals + structured JSON preview.
 * No LiteGraph / ComfyUI deps; vanilla DOM + 2d canvas only.
 *
 * @param {HTMLElement} container mount point (emptied by the editor)
 * @param {object} opts {initialDraft, onDraftChange(draft, caption)}
 * @returns {{getDraft, getJSON, setDraft, destroy}}
 */
export function createLayoutEditor(container, opts) {
  opts = opts || {};
  injectStyle();
  const onDraftChange = typeof opts.onDraftChange === "function" ? opts.onDraftChange : null;

  let draft = normalizeDraft(opts.initialDraft || loadPersistedDraft() || blankDraft());
  let selection = new Set();
  let activeIdx = draft.boxes.length ? 0 : -1;
  if (activeIdx >= 0) selection.add(activeIdx);
  let destroyed = false;
  let bgImg = null; // local file-upload background (ComfyUI Live/Grab BG omitted; see header)
  let bgUrl = "";
  let altCycle = 0;
  let hoveredSwatch = null; // {get,set} for Ctrl+C/V hex copy (upstream swatch row 2266-2380)

  const wrap = el("div", "stlay-wrap");
  container.innerHTML = "";
  container.appendChild(wrap);

  // ---- Scene: overall image setup (dims + description + background + style).
  // Kept visually separate from per-element editing below.
  const scene = el("div", "stlay-scene");
  scene.appendChild(el("div", "stlay-sect", "Scene — overall image setup"));
  const dimsRow = el("div", "stlay-bar");
  const wInput = el("input", "stlay-field");
  wInput.type = "number"; wInput.min = String(DIM_MIN); wInput.step = String(DIM_STEP);
  wInput.style.width = "76px"; wInput.title = "Canvas width (multiples of 16)";
  const hInput = el("input", "stlay-field");
  hInput.type = "number"; hInput.min = String(DIM_MIN); hInput.step = String(DIM_STEP);
  hInput.style.width = "76px"; hInput.title = "Canvas height (multiples of 16)";
  const copyBtn = el("button", "stlay-btn", "Copy JSON");
  // Oracle P1-10: honest destructive label — scene fields are kept, only
  // regions go. (No confirm dialog: headless/automation dismissals would
  // silently cancel the action, and suites + users need it to just work.)
  const clearBtn = el("button", "stlay-btn", "Clear regions");
  clearBtn.title = "Delete all regions (scene settings are kept)";
  const tokenSpan = el("span", "stlay-lbl", "");
  tokenSpan.title = "Rough token estimate (~chars/4)";
  dimsRow.appendChild(el("span", "stlay-lbl", "W"));
  dimsRow.appendChild(wInput);
  dimsRow.appendChild(el("span", "stlay-lbl", "H"));
  dimsRow.appendChild(hInput);
  scene.appendChild(dimsRow);
  // Canvas toolbar: actions that operate on the composition (not the scene).
  const bar = el("div", "stlay-bar");
  bar.appendChild(copyBtn);
  bar.appendChild(clearBtn);
  bar.appendChild(tokenSpan);
  wrap.appendChild(bar);

  // ---- globals ----
  const globals = el("div", "stlay-bar");
  globals.style.alignItems = "flex-start";
  const hldInput = el("input", "stlay-field");
  hldInput.placeholder = "High-level description (optional, blank = omitted)";
  hldInput.style.flex = "2 1 200px";
  const modeSel = el("select", "stlay-field");
  for (const [v, t] of [["none", "style: none"], ["photo", "style: photo"], ["art_style", "style: art"]]) {
    const o = document.createElement("option");
    o.value = v; o.textContent = t;
    modeSel.appendChild(o);
  }
  modeSel.title = "Style mode";
  globals.appendChild(hldInput);
  globals.appendChild(modeSel);
  scene.appendChild(globals);

  const bgArea = el("textarea", "stlay-area");
  bgArea.placeholder = "Background description (required scene background)";
  bgArea.rows = 2;
  scene.appendChild(bgArea);

  const styleRow = el("div", "stlay-bar");
  const aesInput = el("input", "stlay-field"); aesInput.placeholder = "aesthetics";
  const lightInput = el("input", "stlay-field"); lightInput.placeholder = "lighting";
  const photoInput = el("input", "stlay-field"); photoInput.placeholder = "photo";
  const mediumInput = el("input", "stlay-field"); mediumInput.placeholder = "medium";
  const artInput = el("input", "stlay-field"); artInput.placeholder = "Art style";
  for (const inp of [aesInput, lightInput, photoInput, mediumInput, artInput]) {
    inp.style.flex = "1 1 90px";
    styleRow.appendChild(inp);
  }
  scene.appendChild(styleRow);

  const stylePalBar = el("div", "stlay-bar");
  stylePalBar.appendChild(el("span", "stlay-lbl", "Style colors:"));
  scene.appendChild(stylePalBar);
  // Oracle P0-1: style detail controls must not look usable when they cannot
  // contribute (mode none omits the whole style block from the caption).
  const styleHint = el("div", "stlay-lbl", "Choose Photo or Art to include style settings.");
  scene.appendChild(styleHint);

  // ---- background image (local file only) ----
  const bgBar = el("div", "stlay-bar");
  const bgFile = el("input", "stlay-field");
  bgFile.type = "file"; bgFile.accept = "image/*"; bgFile.title = "Local background image (reference only)";
  const bgClear = el("button", "stlay-btn", "Clear BG");
  const brightRange = el("input", "stlay-field");
  brightRange.type = "range"; brightRange.min = "0"; brightRange.max = "100"; brightRange.step = "1";
  brightRange.style.width = "90px";
  brightRange.title = "Background brightness %";
  const brightLbl = el("span", "stlay-lbl", "");
  bgBar.appendChild(el("span", "stlay-lbl", "Tracing image (editor only):"));
  bgBar.appendChild(bgFile);
  bgBar.appendChild(bgClear);
  // Oracle P1-7: the upload is a local tracing reference only — say so, and
  // keep brightness/Clear parked until an image is actually loaded.
  bgBar.appendChild(bgFile);
  bgBar.appendChild(bgClear);
  bgBar.appendChild(el("span", "stlay-lbl", "Brightness"));
  bgBar.appendChild(brightRange);
  bgBar.appendChild(brightLbl);
  bgBar.appendChild(el("span", "stlay-lbl", "Reference only — not included in the prompt."));
  scene.appendChild(bgBar);
  wrap.appendChild(scene);
  // Oracle P1-7: canvas size configures the layout surface, not the output.
  const sizeNote = el("div", "stlay-lbl", "Canvas size is for layout only — output size is configured separately.");
  scene.appendChild(sizeNote);

  // Oracle P1-3: compact gesture hint under the canvas + expandable shortcut
  // list (same gestures as the canvas tooltip, visible without hovering).
  const hintBar = el("div", "stlay-lbl",
    "Drag empty space to draw · Ctrl/Cmd-drag draws over a region");
  const keysDetails = document.createElement("details");
  keysDetails.className = "stlay-disc";
  const keysSummary = document.createElement("summary");
  keysSummary.textContent = "Canvas shortcuts";
  keysDetails.appendChild(keysSummary);
  keysDetails.appendChild(el("div", "stlay-lbl",
    "Click select · Shift-click toggle / Shift-drag marquee multi-select · " +
    "Alt-click cycles overlapping regions · double-click edits description · " +
    "drag moves · corner/edge handles resize · Del removes · " +
    "Ctrl+C / Ctrl+V / Ctrl+D copy, paste, duplicate · right-click a region for the layer list"));
  // ---- main: large visual canvas (primary) + element side panel ----
  const main = el("div", "stlay-main");
  const cvBox = el("div", "stlay-cv");
  cvBox.style.flex = "3 1 460px";
  const canvas = document.createElement("canvas");
  canvas.className = "stlay-canvas";
  canvas.tabIndex = 0;
  canvas.title = "Drag to draw · Ctrl-drag force-draw over a box · click select · Shift-click toggle · " +
    "Shift-drag marquee · Alt-click cycle overlap · double-click edit desc · Del remove · Ctrl+C/V/D copy/paste/duplicate";
  cvBox.appendChild(canvas);
  const side = el("div", "stlay-side");
  main.appendChild(cvBox);
  main.appendChild(side);
  wrap.appendChild(main);
  wrap.appendChild(hintBar);
  wrap.appendChild(keysDetails);

  const listBox = el("div", "stlay-list");
  const listHead = el("div", "stlay-sect", "Regions — frontmost at top");
  side.appendChild(listHead);
  side.appendChild(listBox);

  const edHead = el("div", "stlay-sect", "Selected element");
  side.appendChild(edHead);
  const edBox = el("div", "");
  side.appendChild(edBox);

  // Canonical structured-JSON viewer: collapsed by default (advanced).
  const jsonDetails = document.createElement("details");
  jsonDetails.className = "stlay-disc";
  const jsonSummary = document.createElement("summary");
  jsonSummary.textContent = "Structured JSON preview (advanced)";
  jsonDetails.appendChild(jsonSummary);
  const pre = el("pre", "stlay-pre", "");
  jsonDetails.appendChild(pre);
  side.appendChild(jsonDetails);

  // ---- utilities: import / export (localStorage only), collapsed ----
  const utilHead = el("div", "stlay-sect", "Import / export");
  wrap.appendChild(utilHead);
  const util = el("div", "stlay-util");
  wrap.appendChild(util);
  // ---- import / templates (localStorage only) ----
  const impDetails = document.createElement("details");
  impDetails.className = "stlay-disc";
  const impSummary = document.createElement("summary");
  impSummary.textContent = "Import caption JSON";
  impSummary.style.cursor = "pointer";
  impDetails.appendChild(impSummary);
  const impArea = el("textarea", "stlay-area");
  impArea.placeholder = "Paste an Ideogram caption JSON…";
  const impRow = el("div", "stlay-bar");
  const impLoad = el("button", "stlay-btn", "Load");
  const impErr = el("span", "stlay-lbl", "");
  impErr.style.color = "#c66";
  impRow.appendChild(impLoad);
  impRow.appendChild(impErr);
  impDetails.appendChild(impArea);
  impDetails.appendChild(impRow);
  impDetails.className = "stlay-disc";
  util.appendChild(impDetails);

  // Oracle P2-12: plain product language for the saved-layout store.
  const tplDetails = document.createElement("details");
  tplDetails.className = "stlay-disc";
  const tplSummary = document.createElement("summary");
  tplSummary.textContent = "Saved layouts";
  tplDetails.appendChild(tplSummary);
  tplDetails.appendChild(el("div", "stlay-lbl", "Saved in this browser."));
  const tplRow = el("div", "stlay-bar");
  const tplName = el("input", "stlay-field");
  tplName.placeholder = "template name";
  tplName.style.flex = "1 1 120px";
  const tplSave = el("button", "stlay-btn", "Save");
  const tplSel = el("select", "stlay-field");
  tplSel.style.flex = "1 1 120px";
  const tplLoad = el("button", "stlay-btn", "Load");
  const tplDel = el("button", "stlay-btn", "Delete");
  tplRow.appendChild(tplName);
  tplRow.appendChild(tplSave);
  tplRow.appendChild(tplSel);
  tplRow.appendChild(tplLoad);
  tplRow.appendChild(tplDel);
  tplDetails.appendChild(tplRow);
  // Templates are scene-level: keep them with the Scene setup.
  scene.appendChild(tplDetails);

  function readTemplates() {
    try {
      const v = JSON.parse(window.localStorage.getItem(LS_TEMPLATES) || "{}");
      return v && typeof v === "object" ? v : {};
    } catch (e) { return {}; }
  }
  function refreshTplSel() {
    tplSel.innerHTML = "";
    for (const name of Object.keys(readTemplates()).sort()) {
      const o = document.createElement("option");
      o.value = name; o.textContent = name;
      tplSel.appendChild(o);
    }
  }
  refreshTplSel();

  // ---- canvas geometry (port of upstream fitCanvas/syncCanvasToDims 803-815) ----
  function fitCanvas() {
    if (destroyed || !cvBox.isConnected) return;
    const availW = cvBox.clientWidth;
    if (availW < 4) return;
    const aspect = draft.width / draft.height;
    let cw = Math.min(availW, 640);
    let ch = cw / aspect;
    const maxH = 420;
    if (ch > maxH) {
      ch = maxH;
      cw = ch * aspect;
    }
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = Math.round(cw) + "px";
    canvas.style.height = Math.round(ch) + "px";
    canvas.width = Math.max(1, Math.round(cw * dpr));
    canvas.height = Math.max(1, Math.round(ch * dpr));
    drawCanvas();
  }

  function toPx(box) {
    const r = canvas.getBoundingClientRect();
    return { x: box.x * r.width, y: box.y * r.height, w: box.w * r.width, h: box.h * r.height };
  }
  function toFrac(px, py) {
    const r = canvas.getBoundingClientRect();
    return { x: px / r.width, y: py / r.height };
  }
  function eventPos(e) {
    const r = canvas.getBoundingClientRect();
    return { px: e.clientX - r.left, py: e.clientY - r.top, w: r.width, h: r.height };
  }

  function boxColor(b, fallback) {
    const src = b.color_palette != null ? b.color_palette : (b.color ? [b.color] : []);
    const pal = paletteUpper(src);
    return pal.length ? pal[0] : (fallback || "#8c8c8c");
  }

  function drawCanvas() {
    if (destroyed) return;
    const dpr = window.devicePixelRatio || 1;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    if (!W || !H) return;
    ctx.save();
    ctx.scale(dpr, dpr);
    const r = canvas.getBoundingClientRect();
    const cw = r.width;
    const ch = r.height;
    // Background: dimmed image or dark canvas.
    if (bgImg) {
      const ir = bgImg.width / bgImg.height;
      const cr = cw / ch;
      let dw;
      let dh;
      if (ir > cr) {
        dh = ch; dw = ch * ir;
      } else {
        dw = cw; dh = cw / ir;
      }
      ctx.drawImage(bgImg, (cw - dw) / 2, (ch - dh) / 2, dw, dh);
      const dim = 1 - draft.bgBrightness / 100;
      if (dim > 0) {
        ctx.fillStyle = "rgba(0,0,0," + dim.toFixed(3) + ")";
        ctx.fillRect(0, 0, cw, ch);
      }
    } else {
      ctx.fillStyle = "#1a1a1a";
      ctx.fillRect(0, 0, cw, ch);
    }
    // Oracle P1-3: an empty canvas invites the first action in-canvas instead
    // of leaving instructions to the side panel.
    if (!draft.boxes.length) {
      ctx.fillStyle = "rgba(200,200,200,0.75)";
      ctx.font = "13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Drag on the canvas to draw a region", cw / 2, ch / 2 - 10);
      ctx.font = "11px sans-serif";
      ctx.fillStyle = "rgba(160,160,160,0.75)";
      ctx.fillText("New regions start as objects — switch to Text in the side panel", cw / 2, ch / 2 + 12);
      ctx.textAlign = "start";
    }
    // Boxes in array order (later = front).
    draft.boxes.forEach((b, i) => {
      if (b.nobbox) return;
      const p = toPx(b);
      const x1 = Math.min(p.x, p.x + p.w);
      const y1 = Math.min(p.y, p.y + p.h);
      const x2 = Math.max(p.x, p.x + p.w);
      const y2 = Math.max(p.y, p.y + p.h);
      const col = boxColor(b);
      const isActive = i === activeIdx;
      const isSel = selection.has(i);
      ctx.strokeStyle = isActive ? "#46b4e6" : col;
      ctx.lineWidth = isActive ? 3 : isSel ? 2.5 : 2;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      if (b.locked) {
        ctx.fillStyle = "rgba(255,255,255,0.08)";
        ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
      }
      // Tag chip + label (simplified upstream _render_preview 47-130).
      const tag = String(i + 1).padStart(2, "0") + (b.type === "text" ? "T" : "");
      ctx.font = "11px monospace";
      const tw = ctx.measureText(tag).width;
      ctx.fillStyle = isActive ? "#46b4e6" : col;
      ctx.fillRect(x1, y1, tw + 8, 16);
      ctx.fillStyle = "#000";
      ctx.fillText(tag, x1 + 4, y1 + 12);
      const body = b.type === "text" && b.text ? ('"' + b.text + '"') + (b.desc ? " — " + b.desc : "") : (b.desc || "");
      if (body && x2 - x1 > 20 && y2 - y1 > 34) {
        ctx.fillStyle = "rgba(230,230,230,0.92)";
        ctx.font = "11px monospace";
        const words = String(body).split(/\s+/);
        let line = "";
        let ty = y1 + 30;
        for (const word of words) {
          const test = line ? line + " " + word : word;
          if (line && ctx.measureText(test).width > x2 - x1 - 8) {
            ctx.fillText(line, x1 + 4, ty);
            ty += 13;
            if (ty > y2 - 4) break;
            line = word;
          } else {
            line = test;
          }
        }
        if (line && ty <= y2 - 4) ctx.fillText(line, x1 + 4, ty);
      }
      // Resize handles for the active box.
      if (isActive && !b.locked) {
        ctx.fillStyle = "#46b4e6";
        for (const [hx, hy] of handlePositions(x1, y1, x2, y2)) {
          ctx.fillRect(hx - 3, hy - 3, 6, 6);
        }
      }
    });
    // Marquee rect.
    if (drag && drag.mode === "marquee") {
      const r2 = canvas.getBoundingClientRect();
      const x1 = Math.min(drag.startPx, drag.curPx);
      const y1 = Math.min(drag.startPy, drag.curPy);
      ctx.strokeStyle = "#46b4e6";
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(x1, y1, Math.abs(drag.curPx - drag.startPx), Math.abs(drag.curPy - drag.startPy));
      ctx.setLineDash([]);
      void r2;
    }
    ctx.restore();
  }

  function handlePositions(x1, y1, x2, y2) {
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    return [[x1, y1], [mx, y1], [x2, y1], [x1, my], [x2, my], [x1, y2], [mx, y2], [x2, y2]];
  }

  function hitHandle(pos, idx) {
    const b = draft.boxes[idx];
    if (!b || b.nobbox || b.locked) return -1;
    const p = toPx(b);
    const x1 = Math.min(p.x, p.x + p.w);
    const y1 = Math.min(p.y, p.y + p.h);
    const x2 = Math.max(p.x, p.x + p.w);
    const y2 = Math.max(p.y, p.y + p.h);
    const hs = handlePositions(x1, y1, x2, y2);
    for (let k = 0; k < hs.length; k++) {
      if (Math.abs(pos.px - hs[k][0]) <= HANDLE && Math.abs(pos.py - hs[k][1]) <= HANDLE) return k;
    }
    return -1;
  }

  function hitBody(pos, idx) {
    const b = draft.boxes[idx];
    if (!b || b.nobbox) return false;
    const p = toPx(b);
    const x1 = Math.min(p.x, p.x + p.w);
    const y1 = Math.min(p.y, p.y + p.h);
    const x2 = Math.max(p.x, p.x + p.w);
    const y2 = Math.max(p.y, p.y + p.h);
    return pos.px >= x1 && pos.px <= x2 && pos.py >= y1 && pos.py <= y2;
  }

  function boxesAt(pos) {
    // Top-first (front-first) hit list (upstream boxesAt 1572-1599).
    const out = [];
    for (let i = draft.boxes.length - 1; i >= 0; i--) {
      if (hitBody(pos, i)) out.push(i);
    }
    return out;
  }

  let drag = null;

  canvas.addEventListener("pointerdown", (e) => {
    if (destroyed) return;
    canvas.focus();
    if (e.button === 2) return; // context menu handled separately
    if (e.button !== 0) return;
    e.preventDefault();
    try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* noop */ }
    const pos = eventPos(e);
    const f = toFrac(pos.px, pos.py);
    // Resize handle of the active box wins.
    if (activeIdx >= 0 && hitHandle(pos, activeIdx) >= 0) {
      const b = draft.boxes[activeIdx];
      drag = { mode: "resize", handle: hitHandle(pos, activeIdx), idx: activeIdx, start: { x: f.x, y: f.y }, orig: Object.assign({}, b), moved: false };
      return;
    }
    const hits = boxesAt(pos);
    if (e.ctrlKey || e.metaKey) {
      // Ctrl-drag force-draws a new region even atop a box (upstream 1527-1529).
      drag = { mode: "draw", start: { x: f.x, y: f.y }, cur: { x: f.x, y: f.y }, moved: false, tmpIdx: -1 };
      return;
    }
    if (hits.length) {
      let idx = hits[0];
      if (e.altKey && hits.length > 1) {
        // Alt-click cycles overlapping regions (upstream pickForSelection 1572-1599).
        altCycle = (altCycle + 1) % hits.length;
        idx = hits[altCycle];
      } else {
        altCycle = 0;
      }
      const b = draft.boxes[idx];
      if (e.shiftKey) {
        // Shift-click toggles multi-select (upstream 1540-1553).
        if (selection.has(idx)) selection.delete(idx);
        else selection.add(idx);
        activeIdx = idx;
        drawCanvas();
        renderPanel();
        return;
      }
      let pendingCollapse = -1;
      if (selection.has(idx) && selection.size > 1) pendingCollapse = idx;
      else {
        selection = new Set([idx]);
        activeIdx = idx;
      }
      // Move drag over all selected boxes.
      const snap = {};
      for (const si of selection) {
        if (!draft.boxes[si] || draft.boxes[si].locked) continue;
        snap[si] = Object.assign({}, draft.boxes[si]);
      }
      drag = { mode: "move", start: { x: f.x, y: f.y }, snap, pendingCollapse, moved: false };
      drawCanvas();
      renderPanel();
      return;
    }
    if (e.shiftKey) {
      drag = { mode: "marquee", startPx: pos.px, startPy: pos.py, curPx: pos.px, curPy: pos.py, moved: false };
      return;
    }
    // Drag on empty canvas draws a new region (upstream pointer handlers 1512-1569).
    drag = { mode: "draw", start: { x: f.x, y: f.y }, cur: { x: f.x, y: f.y }, moved: false, tmpIdx: -1 };
  });

  canvas.addEventListener("pointermove", (e) => {
    if (!drag || destroyed) return;
    const pos = eventPos(e);
    const f = toFrac(pos.px, pos.py);
    if (drag.mode === "draw") {
      drag.cur = { x: f.x, y: f.y };
      drag.moved = true;
      // Live ghost box (upstream drag update 1719).
      if (drag.tmpIdx >= 0 && draft.boxes[drag.tmpIdx] && draft.boxes[drag.tmpIdx]._ghost) {
        const g = draft.boxes[drag.tmpIdx];
        g.x = Math.min(drag.start.x, drag.cur.x);
        g.y = Math.min(drag.start.y, drag.cur.y);
        g.w = Math.abs(drag.cur.x - drag.start.x);
        g.h = Math.abs(drag.cur.y - drag.start.y);
      } else {
        const g = { id: uid(), type: "obj", x: drag.start.x, y: drag.start.y, w: 0, h: 0, desc: "", text: "", color_palette: [], nobbox: false, locked: false, _ghost: true };
        draft.boxes.push(g);
        drag.tmpIdx = draft.boxes.length - 1;
      }
      drawCanvas();
    } else if (drag.mode === "move") {
      const dx = f.x - drag.start.x;
      const dy = f.y - drag.start.y;
      if (Math.abs(dx) + Math.abs(dy) > 0.001) drag.moved = true;
      for (const key of Object.keys(drag.snap)) {
        const si = Number(key);
        const o = drag.snap[key];
        const b = draft.boxes[si];
        if (!b) continue;
        b.x = clamp01(o.x + dx);
        b.y = clamp01(o.y + dy);
        b.w = o.w;
        b.h = o.h;
      }
      drawCanvas();
    } else if (drag.mode === "resize") {
      const b = draft.boxes[drag.idx];
      if (!b) return;
      drag.moved = true;
      const o = drag.orig;
      const h = drag.handle; // 0 NW,1 N,2 NE,3 W,4 E,5 SW,6 S,7 SE
      let x1 = o.x;
      let y1 = o.y;
      let x2 = o.x + o.w;
      let y2 = o.y + o.h;
      if (h === 0 || h === 3 || h === 5) x1 = f.x;
      if (h === 2 || h === 4 || h === 7) x2 = f.x;
      if (h === 0 || h === 1 || h === 2) y1 = f.y;
      if (h === 5 || h === 6 || h === 7) y2 = f.y;
      b.x = Math.min(x1, x2);
      b.y = Math.min(y1, y2);
      b.w = Math.abs(x2 - x1);
      b.h = Math.abs(y2 - y1);
      normalizeBox(b);
      drawCanvas();
    } else if (drag.mode === "marquee") {
      drag.curPx = pos.px;
      drag.curPy = pos.py;
      drag.moved = true;
      drawCanvas();
    }
  });

  function endDrag(e) {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (d.mode === "draw") {
      // Drop the ghost and commit a real box (discard click-sized ghosts).
      if (d.tmpIdx >= 0 && draft.boxes[d.tmpIdx] && draft.boxes[d.tmpIdx]._ghost) {
        draft.boxes.splice(d.tmpIdx, 1);
      }
      const w = Math.abs(d.cur.x - d.start.x);
      const h = Math.abs(d.cur.y - d.start.y);
      const pos = e && e.clientX != null ? eventPos(e) : null;
      void pos;
      if (d.moved && w > 0.005 && h > 0.005) {
        const nb = { id: uid(), type: "obj", x: Math.min(d.start.x, d.cur.x), y: Math.min(d.start.y, d.cur.y), w, h, desc: "", text: "", color_palette: [], nobbox: false, locked: false };
        normalizeBox(nb);
        draft.boxes.push(nb);
        selection = new Set([draft.boxes.length - 1]);
        activeIdx = draft.boxes.length - 1;
      } else if (!d.moved) {
        selection = new Set();
        activeIdx = -1;
      }
      touch();
    } else if (d.mode === "move") {
      if (!d.moved && d.pendingCollapse >= 0) {
        selection = new Set([d.pendingCollapse]);
        activeIdx = d.pendingCollapse;
      }
      for (const b of draft.boxes) {
        if (b) { normalizeBox(b); delete b._ghost; }
      }
      touch();
    } else if (d.mode === "resize") {
      for (const b of draft.boxes) {
        if (b) { normalizeBox(b); delete b._ghost; }
      }
      touch();
    } else if (d.mode === "marquee") {
      if (d.moved) {
        const r = canvas.getBoundingClientRect();
        const fx1 = Math.min(d.startPx, d.curPx) / r.width;
        const fy1 = Math.min(d.startPy, d.curPy) / r.height;
        const fx2 = Math.max(d.startPx, d.curPx) / r.width;
        const fy2 = Math.max(d.startPy, d.curPy) / r.height;
        selection = new Set();
        draft.boxes.forEach((b, i) => {
          if (!b || b.nobbox) return;
          const bx1 = Math.min(b.x, b.x + b.w);
          const by1 = Math.min(b.y, b.y + b.h);
          const bx2 = Math.max(b.x, b.x + b.w);
          const by2 = Math.max(b.y, b.y + b.h);
          if (bx1 < fx2 && bx2 > fx1 && by1 < fy2 && by2 > fy1) selection.add(i);
        });
        activeIdx = selection.size ? Math.max(...selection) : -1;
      }
      touch();
    }
  }
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", () => { drag = null; for (const b of draft.boxes) if (b) delete b._ghost; drawCanvas(); });

  // Double-click: inline desc edit (upstream dblclick inline desc 1610-1659).
  canvas.addEventListener("dblclick", (e) => {
    const pos = eventPos(e);
    const hits = boxesAt(pos);
    if (!hits.length) return;
    const idx = hits[0];
    const b = draft.boxes[idx];
    if (!b || b.locked) return;
    selection = new Set([idx]);
    activeIdx = idx;
    const p = toPx(b);
    const x1 = Math.min(p.x, p.x + p.w);
    const y1 = Math.min(p.y, p.y + p.h);
    const x2 = Math.max(p.x, p.x + p.w);
    const ta = document.createElement("textarea");
    ta.className = "stlay-inline";
    ta.value = b.desc || "";
    ta.style.left = x1 + "px";
    ta.style.top = y1 + "px";
    ta.style.width = Math.max(80, x2 - x1) + "px";
    ta.style.height = "52px";
    cvBox.style.position = "relative";
    cvBox.appendChild(ta);
    ta.focus();
    ta.select();
    let done = false;
    const commit = (save) => {
      if (done) return;
      done = true;
      if (save) {
        b.desc = ta.value;
        touch();
      }
      ta.remove();
      canvas.focus();
    };
    ta.addEventListener("keydown", (ev) => {
      ev.stopPropagation();
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        commit(true);
      } else if (ev.key === "Escape") {
        ev.preventDefault();
        commit(false);
      }
    });
    ta.addEventListener("blur", () => commit(true));
  });

  // Right-click: select (region list lives in the side panel; upstream menu 1900-2043
  // behaviour is covered by the side region list, so this only selects).
  canvas.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    const pos = eventPos(e);
    const hits = boxesAt(pos);
    if (hits.length) {
      selection = new Set([hits[0]]);
      activeIdx = hits[0];
      touch();
    }
  });

  // Keyboard: delete / copy / paste / duplicate (upstream del/copy/paste/dupe 1661-1717).
  canvas.addEventListener("keydown", (e) => {
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || (e.target && e.target.isContentEditable)) return;
    const ctrl = e.ctrlKey || e.metaKey;
    const key = e.key;
    if ((key === "Delete" || key === "Backspace") && selection.size) {
      e.preventDefault();
      deleteSelected();
    } else if (ctrl && (key === "c" || key === "C")) {
      e.preventDefault();
      copySelected();
    } else if (ctrl && (key === "v" || key === "V")) {
      e.preventDefault();
      pasteClipboard();
    } else if (ctrl && (key === "d" || key === "D")) {
      e.preventDefault();
      duplicateSelected();
    }
  });

  function selectedSorted() {
    return [...selection].filter((i) => draft.boxes[i]).sort((a, b) => a - b);
  }

  function deleteSelected() {
    const idxs = selectedSorted().reverse();
    if (!idxs.length) return;
    for (const i of idxs) {
      if (draft.boxes[i] && !draft.boxes[i].locked) draft.boxes.splice(i, 1);
    }
    selection = new Set();
    activeIdx = draft.boxes.length ? Math.min(activeIdx >= 0 ? activeIdx : 0, draft.boxes.length - 1) : -1;
    if (activeIdx >= 0) selection.add(activeIdx);
    touch();
  }

  function cloneBox(b) {
    const nb = JSON.parse(JSON.stringify(b));
    nb.id = uid();
    delete nb._ghost;
    delete nb.locked;
    return nb;
  }

  function copySelected() {
    const idxs = selectedSorted();
    if (!idxs.length) return;
    copiedBoxes = idxs.map((i) => cloneBox(draft.boxes[i]));
  }

  function pasteClipboard() {
    // Paste with a small offset, clamped into the canvas (upstream paste clamp 1667-1692).
    if (!copiedBoxes || !copiedBoxes.length) return;
    const fresh = copiedBoxes.map((b) => {
      const nb = cloneBox(b);
      nb.x = clamp01(nb.x + 0.02);
      nb.y = clamp01(nb.y + 0.02);
      normalizeBox(nb);
      return nb;
    });
    const base = draft.boxes.length;
    for (const nb of fresh) draft.boxes.push(nb);
    selection = new Set(fresh.map((_, k) => base + k));
    activeIdx = base + fresh.length - 1;
    touch();
  }

  function duplicateSelected() {
    copySelected();
    pasteClipboard();
  }

  // ---- swatch row (upstream swatch row 2266-2380, simplified, same interactions) ----
  function makeSwatchRow(getColors, setColors, max) {
    const row = el("div", "stlay-bar");
    function render() {
      row.innerHTML = "";
      const colors = getColors();
      colors.forEach((hex, i) => {
        const sw = document.createElement("div");
        sw.className = "stlay-sw";
        sw.style.background = hex;
        sw.dataset.hex = hex;
        sw.title = hex + " (click pick · drag reorder · right-click remove · hover + Ctrl+C/V copy/paste)";
        const picker = document.createElement("input");
        picker.type = "color";
        picker.value = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex.toLowerCase() : "#888888";
        sw.appendChild(picker);
        // Click picks a color.
        sw.addEventListener("click", (e) => {
          if (sw._dragged) return;
          e.stopPropagation();
          picker.click();
        });
        picker.addEventListener("input", () => {
          const next = getColors().slice();
          next[i] = picker.value.toUpperCase();
          setColors(next);
        });
        // Drag reorders (pointer-based).
        sw.addEventListener("pointerdown", (e) => {
          if (e.button !== 0) return;
          e.stopPropagation();
          sw._dragged = false;
          const startX = e.clientX;
          const move = (me) => {
            if (Math.abs(me.clientX - startX) > 5) sw._dragged = true;
          };
          const up = (ue) => {
            sw.removeEventListener("pointermove", move);
            sw.removeEventListener("pointerup", up);
            if (!sw._dragged) return;
            const sibs = [...row.querySelectorAll(".stlay-sw")];
            let target = sibs.length - 1;
            for (let k = 0; k < sibs.length; k++) {
              const r = sibs[k].getBoundingClientRect();
              if (ue.clientX < r.left + r.width / 2) {
                target = k;
                break;
              }
            }
            const next = getColors().slice();
            const [mv] = next.splice(i, 1);
            next.splice(Math.max(0, Math.min(target, next.length)), 0, mv);
            setColors(next);
            setTimeout(() => { sw._dragged = false; }, 0);
          };
          sw.addEventListener("pointermove", move);
          sw.addEventListener("pointerup", up);
        });
        // Right-click removes.
        sw.addEventListener("contextmenu", (e) => {
          e.preventDefault();
          e.stopPropagation();
          setColors(getColors().filter((_, k) => k !== i));
        });
        // Hover arms Ctrl+C / Ctrl+V hex copy-paste (upstream hoveredSwatch).
        sw.addEventListener("pointerenter", () => {
          hoveredSwatch = {
            get: () => getColors()[i],
            set: (c) => {
              const next = getColors().slice();
              next[i] = String(c).toUpperCase();
              setColors(next);
            },
          };
        });
        sw.addEventListener("pointerleave", () => {
          if (hoveredSwatch && hoveredSwatch.get() === getColors()[i]) hoveredSwatch = null;
        });
        row.appendChild(sw);
      });
      if (colors.length < max) {
        const add = el("button", "stlay-btn", "+");
        add.title = "Add a color (uses the clipboard color if it is one)";
        add.addEventListener("click", async () => {
          let c = null;
          try {
            // Best-effort clipboard color (upstream "+" behavior): race a short
            // timeout because readText() can hang indefinitely where clipboard
            // permission is unavailable (then fall back to the default).
            const txt = await Promise.race([
              navigator.clipboard.readText(),
              new Promise((res) => setTimeout(() => res(""), 300)),
            ]);
            c = parseColorString(txt);
          } catch (e) { /* clipboard unavailable -> default */ }
          setColors(getColors().concat([(c || "#ffffff").toUpperCase()]));
        });
        row.appendChild(add);
      }
    }
    render();
    return { el: row, render };
  }

  document.addEventListener("keydown", (e) => {
    if (!hoveredSwatch || destroyed) return;
    const ctrl = e.ctrlKey || e.metaKey;
    if (!ctrl) return;
    const key = (e.key || "").toLowerCase();
    if (key !== "v" && key !== "c") return;
    const ae = document.activeElement;
    if (ae && (ae.tagName === "TEXTAREA" || ae.tagName === "INPUT" || ae.isContentEditable)) return;
    e.preventDefault();
    e.stopPropagation();
    if (key === "c") {
      try { navigator.clipboard.writeText(hoveredSwatch.get() || ""); } catch (err) { /* noop */ }
    } else {
      navigator.clipboard.readText().then((txt) => {
        const c = parseColorString(txt);
        if (c) hoveredSwatch.set(c);
      }).catch(() => {});
    }
  });

  let styleSwatches = null;
  function renderStylePalette() {
    stylePalBar.querySelectorAll(".stlay-sw, .stlay-btn").forEach((n) => n.remove());
    styleSwatches = makeSwatchRow(
      () => draft.color_palette,
      (next) => {
        draft.color_palette = paletteUpper(next).slice(0, MAX_STYLE_COLORS);
        touch();
      },
      MAX_STYLE_COLORS
    );
    for (const n of [...styleSwatches.el.childNodes]) stylePalBar.appendChild(n);
  }

  // ---- region list + element editor (upstream region list 1900-2043, renderPanel 2421+) ----
  // Oracle P1-9: the geometry disclosure is rebuilt with the panel, so its
  // open state is preserved explicitly instead of snapping shut on every edit.
  let geoOpen = false;
  function rowLabel(b) {
    return (b.desc || (b.type === "text" ? b.text : "") || ("(" + b.type + ")")) +
      (b.nobbox ? " · unpositioned" : "");
  }
  function renderPanel() {
    if (destroyed) return;
    // Region list (front-first display; array order is the source of truth).
    listBox.innerHTML = "";
    for (let li = draft.boxes.length - 1; li >= 0; li--) {
      const b = draft.boxes[li];
      const i = li;
      const r = el("div", "stlay-lrow" + (selection.has(i) ? " active" : ""));
      const chip = el("div", "stlay-lsw");
      chip.style.background = boxColor(b);
      const num = el("span", "stlay-lnum", String(i + 1).padStart(2, "0"));
      const label = rowLabel(b);
      const txt = el("span", "stlay-ltext" + (label.startsWith("(") ? " empty" : ""), label);
      txt.title = label;
      r.appendChild(chip);
      r.appendChild(num);
      r.appendChild(txt);
      const lockBtn = el("button", "stlay-lbtn" + (b.locked ? " on" : ""), b.locked ? "🔒" : "🔓");
      lockBtn.title = b.locked ? "Unlock" : "Lock";
      lockBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        b.locked = !b.locked;
        touch();
      });
      const frontBtn = el("button", "stlay-lbtn", "▲");
      frontBtn.title = "Bring toward front";
      // Oracle P1-5: visually disable what cannot operate (same no-ops as before).
      frontBtn.disabled = i >= draft.boxes.length - 1;
      frontBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (i < draft.boxes.length - 1) {
          const [mv] = draft.boxes.splice(i, 1);
          draft.boxes.splice(i + 1, 0, mv);
          selection = new Set([i + 1]);
          activeIdx = i + 1;
          touch();
        }
      });
      const backBtn = el("button", "stlay-lbtn", "▼");
      backBtn.title = "Send toward back";
      backBtn.disabled = i <= 0;
      backBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (i > 0) {
          const [mv] = draft.boxes.splice(i, 1);
          draft.boxes.splice(i - 1, 0, mv);
          selection = new Set([i - 1]);
          activeIdx = i - 1;
          touch();
        }
      });
      const dupeBtn = el("button", "stlay-lbtn", "⧉");
      dupeBtn.title = "Duplicate";
      dupeBtn.disabled = !!b.locked;
      dupeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (b.locked) return;
        const nb = cloneBox(b);
        nb.x = clamp01(nb.x + 0.02);
        nb.y = clamp01(nb.y + 0.02);
        normalizeBox(nb);
        draft.boxes.splice(i + 1, 0, nb);
        selection = new Set([i + 1]);
        activeIdx = i + 1;
        touch();
      });
      const delBtn = el("button", "stlay-lbtn del", "✕");
      delBtn.title = "Delete";
      delBtn.disabled = !!b.locked;
      delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (b.locked) return;
        draft.boxes.splice(i, 1);
        selection.delete(i);
        if (activeIdx === i) activeIdx = -1;
        touch();
      });
      r.appendChild(lockBtn);
      r.appendChild(frontBtn);
      r.appendChild(backBtn);
      r.appendChild(dupeBtn);
      r.appendChild(delBtn);
      r.addEventListener("click", () => {
        selection = new Set([i]);
        activeIdx = i;
        touch();
      });
      listBox.appendChild(r);
    }
    if (!draft.boxes.length) {
      listBox.appendChild(el("div", "stlay-lbl", "No regions — drag on the canvas to draw one."));
    }
    // Oracle P1-5: tie the inspector to its canvas/list identity.
    edHead.textContent = activeIdx >= 0 && draft.boxes[activeIdx]
      ? "Selected region " + String(activeIdx + 1).padStart(2, "0")
      : "Selected element";
    renderElementEditor();
  }

  function numField(value, onCommit, title) {
    const inp = el("input", "stlay-field");
    inp.type = "number";
    inp.value = String(value);
    inp.title = title;
    inp.style.width = "100%";
    inp.style.boxSizing = "border-box";
    inp.addEventListener("change", () => {
      const v = Number(inp.value);
      if (isFinite(v)) onCommit(v);
    });
    inp.addEventListener("keydown", (e) => e.stopPropagation());
    return inp;
  }

  function renderElementEditor() {
    edBox.innerHTML = "";
    const b = activeIdx >= 0 ? draft.boxes[activeIdx] : null;
    if (!b) {
      edBox.appendChild(el("div", "stlay-lbl", "Select a region to edit it."));
      return;
    }
    const typeRow = el("div", "stlay-bar");
    const typeSel = el("select", "stlay-field");
    for (const [v, t] of [["obj", "object"], ["text", "text"]]) {
      const o = document.createElement("option");
      o.value = v; o.textContent = t;
      typeSel.appendChild(o);
    }
    typeSel.value = b.type === "text" ? "text" : "obj";
    typeSel.title = "Element type (object -> type obj, text -> type text)";
    typeSel.addEventListener("change", () => {
      b.type = typeSel.value === "text" ? "text" : "obj";
      touch();
    });
    const placedLbl = document.createElement("label");
    placedLbl.style.cssText = "display:flex;align-items:center;gap:4px;cursor:pointer;";
    // Oracle P1-8: plain creative language — unchecking keeps the element in
    // the prompt without a fixed position (upstream nobbox), it is not a delete.
    placedLbl.title = "Off: included in the prompt without a fixed position";
    const placedChk = document.createElement("input");
    placedChk.type = "checkbox";
    placedChk.checked = !b.nobbox;
    placedChk.addEventListener("change", () => {
      b.nobbox = !placedChk.checked;
      touch();
    });
    placedLbl.appendChild(placedChk);
    placedLbl.appendChild(document.createTextNode("Specify position"));
    typeRow.appendChild(typeSel);
    typeRow.appendChild(placedLbl);
    edBox.appendChild(typeRow);

    // Oracle P1-4: persistent creative-language labels (placeholders vanish
    // once filled) and literal text first for text regions.
    const descArea = el("textarea", "stlay-area");
    descArea.rows = 2;
    descArea.placeholder = "desc (always emitted)";
    descArea.value = b.desc || "";
    descArea.addEventListener("input", () => {
      b.desc = descArea.value;
      touch(true);
    });
    descArea.addEventListener("keydown", (e) => e.stopPropagation());
    const descHead = el("div", "stlay-lbl", "Appearance / description");

    let textInput = null;
    if (b.type === "text") {
      textInput = el("input", "stlay-field");
      textInput.placeholder = "text (text elements only)";
      textInput.value = b.text || "";
      textInput.style.width = "100%";
      textInput.style.boxSizing = "border-box";
      textInput.addEventListener("input", () => {
        b.text = textInput.value;
        touch(true);
      });
      textInput.addEventListener("keydown", (e) => e.stopPropagation());
      edBox.appendChild(el("div", "stlay-lbl", "Text to display"));
      edBox.appendChild(textInput);
    }
    edBox.appendChild(descHead);
    edBox.appendChild(descArea);

    // Exact geometry lives under a collapsed disclosure (upstream
    // boxToPx/commitPxEdit/commitGridEdit 2350-2418): same editors, not the
    // default focus. A one-line visual summary stays visible.
    const g = normBboxToGrid(b); // [ymin,xmin,ymax,xmax]
    edBox.appendChild(el("div", "stlay-geosum",
      "Box " + String(activeIdx + 1).padStart(2, "0") + " · " +
      Math.round(b.x * 100) + "%, " + Math.round(b.y * 100) + "% · " +
      Math.round(b.w * 100) + " × " + Math.round(b.h * 100) + "%" +
      (b.nobbox ? " · unplaced" : "")));
    const geoDetails = document.createElement("details");
    geoDetails.className = "stlay-disc";
    const geoSummary = document.createElement("summary");
    geoSummary.textContent = "Advanced Geometry";
    geoDetails.appendChild(geoSummary);
    geoDetails.open = geoOpen;
    geoDetails.addEventListener("toggle", () => { geoOpen = geoDetails.open; });
    edBox.appendChild(geoDetails);
    // Editable px + 0-1000 grid fields (upstream boxToPx/commitPxEdit/commitGridEdit 2350-2418).
    geoDetails.appendChild(el("div", "stlay-lbl", "bbox px (canvas " + draft.width + "×" + draft.height + ")"));
    const pxGrid = el("div", "stlay-grid2");
    const px = { x: Math.round(b.x * draft.width), y: Math.round(b.y * draft.height), w: Math.round(b.w * draft.width), h: Math.round(b.h * draft.height) };
    for (const k of ["x", "y", "w", "h"]) {
      pxGrid.appendChild(numField(px[k], (v) => {
        const f = k === "x" || k === "w" ? v / draft.width : v / draft.height;
        if (k === "x") b.x = f;
        else if (k === "y") b.y = f;
        else if (k === "w") b.w = Math.max(0, f);
        else b.h = Math.max(0, f);
        b.nobbox = false;
        normalizeBox(b);
        touch();
      }, "bbox " + k + " in px"));
    }
    geoDetails.appendChild(pxGrid);
    geoDetails.appendChild(el("div", "stlay-lbl", "bbox 0-1000 grid"));
    const gridRow = el("div", "stlay-grid2");
    const grid = normBboxToGrid(b); // [ymin,xmin,ymax,xmax]
    const keys = ["ymin", "xmin", "ymax", "xmax"];
    grid.forEach((gv, gi) => {
      gridRow.appendChild(numField(gv, (v) => {
        // Rebuild fractions from the edited grid corner (upstream commitGridEdit).
        const g = normBboxToGrid(b);
        const nv = [g[0], g[1], g[2], g[3]];
        nv[gi] = Math.max(0, Math.min(1000, Math.round(v)));
        b.x = Math.min(nv[1], nv[3]) / 1000;
        b.y = Math.min(nv[0], nv[2]) / 1000;
        b.w = Math.abs(nv[3] - nv[1]) / 1000;
        b.h = Math.abs(nv[2] - nv[0]) / 1000;
        b.nobbox = false;
        normalizeBox(b);
        touch();
      }, "bbox " + keys[gi] + " (0-1000)"));
    });
    geoDetails.appendChild(gridRow);

    edBox.appendChild(el("div", "stlay-lbl", "Element colors · up to 5 — click a swatch to change it, right-click to remove it"));
    const palRow = makeSwatchRow(
      () => b.color_palette,
      (next) => {
        b.color_palette = paletteUpper(next).slice(0, MAX_ELEM_COLORS);
        touch();
      },
      MAX_ELEM_COLORS
    );
    edBox.appendChild(palRow.el);
  }

  // ---- commit / serialize (upstream serialize/commit/touch 1466-1487) ----
  let syncing = false;
  function syncInputs() {
    syncing = true;
    wInput.value = String(draft.width);
    hInput.value = String(draft.height);
    hldInput.value = draft.high_level_description || "";
    modeSel.value = draft.style_mode;
    bgArea.value = draft.background || "";
    aesInput.value = draft.aesthetics || "";
    lightInput.value = draft.lighting || "";
    photoInput.value = draft.photo || "";
    photoInput.style.display = draft.style_mode === "photo" ? "" : "none";
    mediumInput.value = draft.medium || "";
    mediumInput.style.display = draft.style_mode === "none" ? "none" : "";
    artInput.value = draft.art_style || "";
    artInput.style.display = draft.style_mode === "art_style" ? "" : "none";
    // Oracle P0-1: style block is omitted unless a style mode is chosen, so
    // the detail controls go honestly inactive instead of silently dead.
    const styleActive = draft.style_mode === "photo" || draft.style_mode === "art_style";
    for (const inp of [aesInput, lightInput, photoInput, mediumInput, artInput]) inp.disabled = !styleActive;
    styleRow.style.opacity = styleActive ? "" : "0.45";
    stylePalBar.style.opacity = styleActive ? "" : "0.45";
    for (const b of stylePalBar.querySelectorAll("button")) b.disabled = !styleActive;
    styleHint.style.display = styleActive ? "none" : "";
    brightRange.value = String(draft.bgBrightness);
    brightLbl.textContent = String(draft.bgBrightness) + "%";
    syncing = false;
  }

  function touch(light) {
    if (destroyed) return;
    for (const b of draft.boxes) if (b) delete b._ghost;
    // Normalize in place (same rules as normalizeDraft, same object identity):
    // normalizeDraft() rebuilds every box as a fresh object, which detaches the
    // closures held by focused side-panel inputs (desc/text/palette/px-grid) so
    // only the first keystroke lands. Touch only re-normalizes the live draft.
    draft.boxes = draft.boxes.filter((b) => b && typeof b === "object");
    for (const b of draft.boxes) {
      const rawType = b.type != null ? b.type : b.kind;
      b.type = rawType === "text" ? "text" : "obj";
      b.desc = b.desc != null ? String(b.desc) : (b.label != null ? String(b.label) : "");
      b.text = b.text != null ? String(b.text) : "";
      b.color_palette = paletteUpper(b.color_palette != null ? b.color_palette : (b.color ? [b.color] : [])).slice(0, MAX_ELEM_COLORS);
      b.nobbox = !!b.nobbox;
      b.locked = !!b.locked;
      if (typeof b.id !== "string" || !b.id) b.id = uid();
      normalizeBox(b);
    }
    draft.style_mode = draft.style_mode === "photo" || draft.style_mode === "art_style" ? draft.style_mode : "none";
    draft.color_palette = paletteUpper(draft.color_palette).slice(0, MAX_STYLE_COLORS);
    if (activeIdx >= draft.boxes.length) activeIdx = draft.boxes.length - 1;
    if (activeIdx >= 0) selection.add(activeIdx);
    selection = new Set([...selection].filter((i) => draft.boxes[i]));
    syncInputs();
    renderStylePalette();
    drawCanvas();
    if (!light) renderPanel();
    else {
      // Light touch (typing desc/text): refresh preview + the active list
      // label/chip without rebuilding the focused editor (Oracle P1-9).
      const built = buildIdeogramCaption(draft);
      pre.textContent = JSON.stringify(built.json, null, 2);
      tokenSpan.textContent = "~" + Math.round(built.text.length / 4) + " tok";
      const ab = draft.boxes[activeIdx];
      const row = ab ? listBox.childNodes[draft.boxes.length - 1 - activeIdx] : null;
      if (ab && row && row.querySelector) {
        const t = row.querySelector(".stlay-ltext");
        if (t) {
          const label = rowLabel(ab);
          t.textContent = label;
          t.title = label;
          t.classList.toggle("empty", label.startsWith("("));
        }
        const chip = row.querySelector(".stlay-lsw");
        if (chip) chip.style.background = boxColor(ab);
      }
    }
    const built = buildIdeogramCaption(draft);
    if (!light) {
      pre.textContent = JSON.stringify(built.json, null, 2);
      tokenSpan.textContent = "~" + Math.round(built.text.length / 4) + " tok";
    }
    persistDraft(draft);
    if (onDraftChange) {
      try { onDraftChange(cloneDraft(draft), built); } catch (e) { /* host errors must not break editing */ }
    }
  }

  // ---- wiring ----
  wInput.addEventListener("change", () => {
    if (syncing) return;
    draft.width = snapDim(wInput.value);
    fitCanvas();
    touch(true);
    renderPanel();
  });
  hInput.addEventListener("change", () => {
    if (syncing) return;
    draft.height = snapDim(hInput.value);
    fitCanvas();
    touch(true);
    renderPanel();
  });
  hldInput.addEventListener("input", () => {
    if (syncing) return;
    draft.high_level_description = hldInput.value;
    touch(true);
  });
  modeSel.addEventListener("change", () => {
    if (syncing) return;
    draft.style_mode = modeSel.value;
    touch();
  });
  bgArea.addEventListener("input", () => {
    if (syncing) return;
    draft.background = bgArea.value;
    touch(true);
  });
  for (const [inp, key] of [[aesInput, "aesthetics"], [lightInput, "lighting"], [photoInput, "photo"], [mediumInput, "medium"], [artInput, "art_style"]]) {
    inp.addEventListener("input", () => {
      if (syncing) return;
      draft[key] = inp.value;
      touch(true);
    });
    inp.addEventListener("keydown", (e) => e.stopPropagation());
  }
  for (const inp of [wInput, hInput, hldInput, modeSel, bgArea]) {
    inp.addEventListener("keydown", (e) => e.stopPropagation());
  }
  brightRange.addEventListener("input", () => {
    draft.bgBrightness = Math.max(0, Math.min(100, Math.round(Number(brightRange.value))));
    brightLbl.textContent = String(draft.bgBrightness) + "%";
    drawCanvas();
    persistDraft(draft);
  });
  brightRange.addEventListener("change", () => touch(true));
  // Oracle P1-7: brightness/Clear only make sense with a tracing image.
  function syncBgBar() {
    const has = !!bgImg;
    brightRange.style.display = has ? "" : "none";
    bgClear.style.display = has ? "" : "none";
  }
  bgFile.addEventListener("change", () => {
    const f = bgFile.files && bgFile.files[0];
    if (!f) return;
    if (bgUrl) URL.revokeObjectURL(bgUrl);
    bgUrl = URL.createObjectURL(f);
    const img = new Image();
    img.onload = () => {
      bgImg = img;
      syncBgBar();
      drawCanvas();
    };
    img.src = bgUrl;
  });
  bgClear.addEventListener("click", () => {
    bgImg = null;
    if (bgUrl) {
      URL.revokeObjectURL(bgUrl);
      bgUrl = "";
    }
    bgFile.value = "";
    syncBgBar();
    drawCanvas();
  });
  syncBgBar();
  copyBtn.addEventListener("click", () => {
    const built = buildIdeogramCaption(draft);
    try {
      navigator.clipboard.writeText(built.text);
    } catch (e) { /* clipboard unavailable */ }
  });
  clearBtn.addEventListener("click", () => {
    draft.boxes = [];
    selection = new Set();
    activeIdx = -1;
    touch();
  });
  impLoad.addEventListener("click", () => {
    // Import via the _loads_caption/_repair_json port (upstream 180-207).
    const cap = parseCaptionString(impArea.value);
    if (!cap) {
      impErr.textContent = "Not a valid caption JSON.";
      return;
    }
    impErr.textContent = "";
    const parsed = parseIdeogramCaption(cap);
    // Captions carry no canvas dims: keep the current width/height/brightness.
    parsed.width = draft.width;
    parsed.height = draft.height;
    parsed.bgBrightness = draft.bgBrightness;
    draft = normalizeDraft(parsed);
    selection = new Set();
    activeIdx = draft.boxes.length ? 0 : -1;
    if (activeIdx >= 0) selection.add(activeIdx);
    impArea.value = "";
    impDetails.open = false;
    touch();
  });
  tplSave.addEventListener("click", () => {
    const name = (tplName.value || "").trim();
    if (!name) return;
    const all = readTemplates();
    all[name] = buildIdeogramCaption(draft).text;
    try {
      window.localStorage.setItem(LS_TEMPLATES, JSON.stringify(all));
    } catch (e) { /* quota -> ignore */ }
    tplName.value = "";
    refreshTplSel();
    tplSel.value = name;
  });
  tplLoad.addEventListener("click", () => {
    const name = tplSel.value;
    const raw = readTemplates()[name];
    if (!raw) return;
    const cap = parseCaptionString(raw);
    if (!cap) return;
    const parsed = parseIdeogramCaption(cap);
    parsed.width = draft.width;
    parsed.height = draft.height;
    parsed.bgBrightness = draft.bgBrightness;
    draft = normalizeDraft(parsed);
    selection = new Set();
    activeIdx = draft.boxes.length ? 0 : -1;
    if (activeIdx >= 0) selection.add(activeIdx);
    touch();
  });
  tplDel.addEventListener("click", () => {
    const name = tplSel.value;
    if (!name) return;
    const all = readTemplates();
    delete all[name];
    try {
      window.localStorage.setItem(LS_TEMPLATES, JSON.stringify(all));
    } catch (e) { /* ignore */ }
    refreshTplSel();
  });

  const ro = (typeof ResizeObserver !== "undefined") ? new ResizeObserver(() => fitCanvas()) : null;
  if (ro) ro.observe(cvBox);

  // Initial paint (including the structured preview: renderPanel only owns
  // the rows/inspector, so refresh pre/token/draft-canvas explicitly —
  // otherwise a remount with a restored draft shows rows but an empty
  // preview until the next edit).
  syncInputs();
  renderStylePalette();
  renderPanel();
  const initBuilt = buildIdeogramCaption(draft);
  pre.textContent = JSON.stringify(initBuilt.json, null, 2);
  tokenSpan.textContent = "~" + Math.round(initBuilt.text.length / 4) + " tok";
  drawCanvas();
  requestAnimationFrame(fitCanvas);

  return {
    getDraft() {
      return cloneDraft(draft);
    },
    getJSON() {
      return buildIdeogramCaption(draft).json;
    },
    setDraft(next) {
      // Merge: captions/drafts without canvas dims keep the current ones.
      const cur = { width: draft.width, height: draft.height, bgBrightness: draft.bgBrightness };
      draft = normalizeDraft(Object.assign({}, cur, next || {}));
      selection = new Set();
      activeIdx = draft.boxes.length ? 0 : -1;
      if (activeIdx >= 0) selection.add(activeIdx);
      fitCanvas();
      touch();
    },
    destroy() {
      destroyed = true;
      drag = null;
      hoveredSwatch = null;
      try { if (ro) ro.disconnect(); } catch (e) { /* noop */ }
      if (bgUrl) {
        try { URL.revokeObjectURL(bgUrl); } catch (e) { /* noop */ }
        bgUrl = "";
      }
      bgImg = null;
      wrap.remove();
    },
  };
}
