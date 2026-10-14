// Studio KJNodes layout editor — unit tests (no browser, plain Node).
//
// Covers web/studio-layout-editor.js contracts against the real module:
//   normBboxToGrid (0-1000 rounding/clamp/sort/yx-axis),
//   buildIdeogramCaption (caption shape, style omission rules, obj/text
//   rules, nobbox, palette caps), parseIdeogramCaption (fraction restore,
//   nobbox placeholders, lenient repair, palette caps), legacy percent-store
//   migration, kj-key persistence reload, round-trip stability, canvas
//   draw/select/move/resize + Alt-cycle + keyboard delete/duplicate, globals,
//   element palettes, bbox px/grid sync, import/templates.
//
// createLayoutEditor is vanilla DOM+canvas, so these tests install a minimal
// DOM stub (elements, canvas 2d context, localStorage). Pointer/keyboard
// flows that need a real layout engine (marquee rubber-band visuals,
// palette drag-reorder) stay in tests/browser/studio-layout-editor.spec.mjs.
//
// Run: node tests/studio_layout_editor_unit.mjs

import assert from "node:assert/strict";

// ── Minimal DOM stub ─────────────────────────────────────────────────────
// Only what createLayoutEditor touches during mount + the tested flows:
// createElement/appendChild/listeners, canvas getContext/getBoundingClientRect
// (fixed 300x300 so fractions are deterministic), window.localStorage,
// navigator.clipboard, requestAnimationFrame. fitCanvas early-returns because
// cvBox.isConnected is falsy, so no layout engine is needed.

function makeCtx() {
  return new Proxy({}, {
    get(t, p) {
      if (p === "measureText") return () => ({ width: 10 });
      if (p === Symbol.toPrimitive) return () => 0;
      return () => undefined;
    },
    set() { return true; },
  });
}

function makeElement(tag) {
  const el = {
    tagName: String(tag || "div").toUpperCase(),
    children: [],
    childNodes: [],
    parentNode: null,
    style: {},
    dataset: {},
    className: "",
    textContent: "",
    value: "",
    _listeners: {},
    _html: "",
    isConnected: false,
    clientWidth: 0,
    getBoundingClientRect() { return { left: 0, top: 0, width: 300, height: 300 }; },
    getContext() { return makeCtx(); },
    appendChild(c) {
      el.children.push(c);
      el.childNodes.push(c);
      if (c && typeof c === "object") c.parentNode = el;
      return c;
    },
    removeChild(c) {
      el.children = el.children.filter((k) => k !== c);
      el.childNodes = el.childNodes.filter((k) => k !== c);
      if (c && typeof c === "object" && c.parentNode === el) c.parentNode = null;
      return c;
    },
    addEventListener(t, fn) { (el._listeners[t] = el._listeners[t] || []).push(fn); },
    removeEventListener(t, fn) { el._listeners[t] = (el._listeners[t] || []).filter((f) => f !== fn); },
    querySelectorAll() { return []; },
    remove() { if (el.parentNode) el.parentNode.removeChild(el); },
    focus() {},
    select() {},
    click() {},
    setPointerCapture() {},
  };
  Object.defineProperty(el, "innerHTML", {
    configurable: true,
    get() { return el._html; },
    set(v) { el._html = String(v); el.children = []; el.childNodes = []; },
  });
  return el;
}

const __store = new Map();
const localStorageStub = {
  getItem(k) { const key = String(k); return __store.has(key) ? __store.get(key) : null; },
  setItem(k, v) { __store.set(String(k), String(v)); },
  removeItem(k) { __store.delete(String(k)); },
  clear() { __store.clear(); },
};

const documentStub = {
  createElement: (t) => makeElement(t),
  createTextNode: (t) => ({ textContent: String(t), nodeType: 3, parentNode: null }),
  getElementById: () => null,
  addEventListener() {},
  removeEventListener() {},
  activeElement: null,
  head: makeElement("head"),
  body: makeElement("body"),
};

globalThis.window = {
  localStorage: localStorageStub,
  devicePixelRatio: 1,
};
globalThis.document = documentStub;
Object.defineProperty(globalThis, "navigator", {
  value: {
    clipboard: {
      readText: async () => "",
      writeText: async () => {},
    },
  },
  configurable: true,
  writable: true,
});
globalThis.requestAnimationFrame = () => 0;

const KJ_KEY = "comfymodal.studio.layout.kj.v1";
const LEGACY_KEY = "comfymodal.studio.layout.v1";

const {
  normBboxToGrid,
  buildIdeogramCaption,
  parseIdeogramCaption,
  createLayoutEditor,
} = await import("../web/studio-layout-editor.js");

// ── Helpers ──────────────────────────────────────────────────────────────

function approx(a, b, eps = 1e-9) {
  assert.ok(Math.abs(a - b) <= eps, `expected ${a} ≈ ${b}`);
}

function walk(root, out = []) {
  out.push(root);
  for (const c of (root.children || [])) {
    if (c && c.children) walk(c, out);
    else if (c) out.push(c);
  }
  return out;
}

function qAll(root, pred) {
  return walk(root).filter((n) => n && typeof n === "object" && pred(n));
}

function q(root, pred) {
  const found = qAll(root, pred);
  assert.ok(found.length, "expected to find element");
  return found[0];
}

function hasClass(n, cls) {
  return (n.className || "").split(" ").includes(cls);
}

// Fire stub listeners; awaits async handlers (e.g. clipboard "+ color").
async function fire(el, type, props = {}) {
  const e = { preventDefault() {}, stopPropagation() {}, target: el, ...props };
  const fns = ((el._listeners || {})[type] || []).slice();
  const out = [];
  for (const fn of fns) out.push(fn(e));
  await Promise.all(out);
  return e;
}

function mountEditor(initialDraft) {
  const container = documentStub.createElement("div");
  const changes = [];
  const opts = {
    onDraftChange: (d, b) => { changes.push({ draft: d, built: b }); },
  };
  if (initialDraft !== undefined) opts.initialDraft = initialDraft;
  const handle = createLayoutEditor(container, opts);
  return { container, handle, changes };
}

function activeRowIndex(container) {
  const rows = qAll(container, (n) => n.tagName === "DIV" && hasClass(n, "stlay-lrow"));
  return rows.findIndex((r) => hasClass(r, "active"));
}

function canvasOf(container) {
  return q(container, (n) => n.tagName === "CANVAS");
}

function pointerDown(container, x, y, extra = {}) {
  return fire(canvasOf(container), "pointerdown", {
    button: 0, clientX: x, clientY: y, pointerId: 1,
    ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...extra,
  });
}

function pointerMove(container, x, y, extra = {}) {
  return fire(canvasOf(container), "pointermove", {
    button: 0, clientX: x, clientY: y, pointerId: 1,
    ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...extra,
  });
}

function pointerUp(container, x = 0, y = 0) {
  return fire(canvasOf(container), "pointerup", { clientX: x, clientY: y });
}

function canvasKey(container, key, extra = {}) {
  return fire(canvasOf(container), "keydown", {
    key, target: { tagName: "CANVAS" },
    ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...extra,
  });
}

// ── 1. normBboxToGrid: rounding / clamp / sort / yx axis ──────────────────

{
  // Axis order is yx: [ymin, xmin, ymax, xmax] on the 0-1000 grid.
  assert.deepEqual(normBboxToGrid({ x: 0.1, y: 0.2, w: 0.3, h: 0.4 }), [200, 100, 600, 400]);
  console.log("PASS: norm axis order is yx ([ymin,xmin,ymax,xmax])");
}

{
  // Rounding to ints.
  assert.deepEqual(normBboxToGrid({ x: 0.0004, y: 0, w: 0, h: 0 })[1], 0);
  assert.deepEqual(normBboxToGrid({ x: 0.0005, y: 0, w: 0, h: 0 })[1], 1);
  assert.deepEqual(normBboxToGrid({ x: 0.123456, y: 0, w: 0, h: 0 })[1], 123);
  console.log("PASS: norm rounds extents to ints on the 0-1000 grid");
}

{
  // Clamp each extent to 0..1000.
  assert.deepEqual(normBboxToGrid({ x: -0.5, y: -2, w: 0.1, h: 0.1 }), [0, 0, 0, 0]);
  assert.deepEqual(normBboxToGrid({ x: -0.5, y: 0.1, w: 0.7, h: 0.1 }), [100, 0, 200, 200]);
  assert.deepEqual(normBboxToGrid({ x: 0.9, y: 0.9, w: 0.5, h: 0.5 }), [900, 900, 1000, 1000]);
  // Missing/NaN extents degrade to 0, never NaN.
  assert.deepEqual(normBboxToGrid({}), [0, 0, 0, 0]);
  assert.deepEqual(normBboxToGrid({ x: NaN, y: "junk", w: null, h: undefined }), [0, 0, 0, 0]);
  console.log("PASS: norm clamps to 0..1000 and degrades bad input to 0");
}

{
  // Reversed extents sort (negative w/h flip to min/max).
  assert.deepEqual(normBboxToGrid({ x: 0.5, y: 0.5, w: -0.2, h: -0.1 }), [400, 300, 500, 500]);
  console.log("PASS: norm sorts reversed extents");
}

// ── 2. buildIdeogramCaption: shape / style omission / obj-text / nobbox ───

{
  const built = buildIdeogramCaption({});
  assert.deepEqual(Object.keys(built.json), ["compositional_deconstruction"]);
  assert.deepEqual(built.json.compositional_deconstruction, { background: "", elements: [] });
  assert.equal(JSON.parse(built.text).compositional_deconstruction.elements.length, 0);
  assert.ok(!("high_level_description" in built.json), "blank hld omitted");
  assert.ok(!("style_description" in built.json), "style none omitted");
  console.log("PASS: caption empty shape omits blank hld and style block");
}

{
  const built = buildIdeogramCaption({ high_level_description: "  epic vista  " });
  assert.equal(built.json.high_level_description, "  epic vista  ");
  const blank = buildIdeogramCaption({ high_level_description: "   " });
  assert.ok(!("high_level_description" in blank.json));
  console.log("PASS: caption keeps hld verbatim, omits whitespace-only hld");
}

{
  // Photo mode: every style key present (blanks kept), no art_style.
  const built = buildIdeogramCaption({ style_mode: "photo", aesthetics: "clean", medium: "digital" });
  const sd = built.json.style_description;
  assert.deepEqual(Object.keys(sd), ["aesthetics", "lighting", "photo", "medium"]);
  assert.equal(sd.aesthetics, "clean");
  assert.equal(sd.lighting, "");
  assert.equal(sd.medium, "digital");
  assert.ok(!("art_style" in sd));
  // Art mode: medium + art_style, no photo.
  const art = buildIdeogramCaption({ style_mode: "art_style", art_style: "anime" });
  assert.deepEqual(Object.keys(art.json.style_description), ["aesthetics", "lighting", "medium", "art_style"]);
  assert.ok(!("photo" in art.json.style_description));
  // Empty style palette omitted; non-empty uppercased + capped at 16.
  assert.ok(!("color_palette" in sd));
  const pal = buildIdeogramCaption({
    style_mode: "photo",
    color_palette: Array.from({ length: 20 }, (_, i) => "#ab000" + (i % 10)),
  });
  assert.equal(pal.json.style_description.color_palette.length, 16);
  assert.ok(pal.json.style_description.color_palette.every((c) => c === c.toUpperCase()));
  // Any non-"none"/non-"photo" mode takes the art branch (normalizeDraft
  // coerces unknown modes to "none" before build ever sees them).
  assert.deepEqual(
    Object.keys(buildIdeogramCaption({ style_mode: "bogus" }).json.style_description),
    ["aesthetics", "lighting", "medium", "art_style"]
  );
  console.log("PASS: caption style omission rules + photo/art key sets + style palette cap 16");
}

{
  const built = buildIdeogramCaption({
    background: "city",
    boxes: [
      { type: "obj", x: 0.1, y: 0.2, w: 0.3, h: 0.4, desc: "car", color_palette: ["#ff0000", " #00ff00 "] },
      { type: "text", x: 0, y: 0, w: 0.2, h: 0.1, desc: "sign", text: "SHOP" },
      { type: "obj", x: 0.5, y: 0.5, w: 0.1, h: 0.1, nobbox: true },
      { kind: "text", label: "legacy", color: "#abc", text: "HI", x: 0.1, y: 0.1, w: 0.1, h: 0.1 },
    ],
  });
  const els = built.json.compositional_deconstruction.elements;
  assert.equal(els.length, 4);
  // type is always the first key (upstream order).
  for (const e of els) assert.equal(Object.keys(e)[0], "type");
  // obj: bbox + desc + upper palette, never text.
  assert.deepEqual(els[0].bbox, [200, 100, 600, 400]);
  assert.ok(!("text" in els[0]));
  assert.deepEqual(els[0].color_palette, ["#FF0000", "#00FF00"]);
  // text: exact text preserved, desc always emitted.
  assert.equal(els[1].text, "SHOP");
  assert.equal(els[1].desc, "sign");
  // nobbox: unplaced elements omit bbox but keep desc.
  assert.ok(!("bbox" in els[2]));
  assert.equal(els[2].desc, "");
  // Legacy box shape (kind/label/color) degrades through the same rules.
  assert.equal(els[3].type, "text");
  assert.equal(els[3].desc, "legacy");
  assert.equal(els[3].text, "HI");
  assert.deepEqual(els[3].color_palette, ["#ABC"]);
  // Per-element palette capped at 5.
  const many = buildIdeogramCaption({
    boxes: [{ type: "obj", x: 0, y: 0, w: 0.1, h: 0.1, color_palette: ["#111111", "#222222", "#333333", "#444444", "#555555", "#666666", "#777777"] }],
  });
  assert.equal(many.json.compositional_deconstruction.elements[0].color_palette.length, 5);
  assert.equal(built.json.compositional_deconstruction.background, "city");
  console.log("PASS: caption obj/text rules, nobbox omission, legacy fallbacks, element palette cap 5");
}

// ── 3. parseIdeogramCaption ───────────────────────────────────────────────

{
  const draft = parseIdeogramCaption({
    high_level_description: "epic",
    style_description: { aesthetics: "clean", lighting: "soft", photo: "35mm", medium: "digital", color_palette: ["#aabbcc"] },
    compositional_deconstruction: {
      background: "city",
      elements: [
        { type: "obj", bbox: [200, 100, 600, 400], desc: "car", color_palette: ["#ff0000"] },
        { type: "text", text: "SHOP", desc: "sign" },
      ],
    },
  });
  assert.equal(draft.high_level_description, "epic");
  assert.equal(draft.style_mode, "photo");
  assert.equal(draft.background, "city");
  const b = draft.boxes[0];
  approx(b.x, 0.1); approx(b.y, 0.2); approx(b.w, 0.3); approx(b.h, 0.4);
  assert.equal(b.type, "obj");
  assert.equal(b.desc, "car");
  assert.deepEqual(b.color_palette, ["#FF0000"]);
  // Missing bbox -> unplaced placeholder.
  assert.equal(draft.boxes[1].nobbox, true);
  assert.equal(draft.boxes[1].text, "SHOP");
  console.log("PASS: parse restores fractions, photo style, nobbox placeholders");
}

{
  // Reversed bbox sorts to the same fractions.
  const fwd = parseIdeogramCaption({ compositional_deconstruction: { background: "", elements: [{ type: "obj", bbox: [200, 100, 600, 400], desc: "" }] } });
  const rev = parseIdeogramCaption({ compositional_deconstruction: { background: "", elements: [{ type: "obj", bbox: [600, 400, 200, 100], desc: "" }] } });
  for (const k of ["x", "y", "w", "h"]) approx(fwd.boxes[0][k], rev.boxes[0][k]);
  // art_style key selects art mode; bare aesthetics defaults to photo.
  const art = parseIdeogramCaption({ style_description: { medium: "m", art_style: "a" }, compositional_deconstruction: { background: "", elements: [] } });
  assert.equal(art.style_mode, "art_style");
  assert.equal(art.art_style, "a");
  const bare = parseIdeogramCaption({ style_description: { aesthetics: "x" }, compositional_deconstruction: { background: "", elements: [] } });
  assert.equal(bare.style_mode, "photo");
  console.log("PASS: parse sorts reversed bbox + detects style mode");
}

{
  // String input + lenient repair (trailing comma) work; garbage -> blank.
  const fromStr = parseIdeogramCaption('{"high_level_description": "hi",}');
  assert.equal(fromStr.high_level_description, "hi");
  assert.deepEqual(parseIdeogramCaption("").boxes, []);
  assert.deepEqual(parseIdeogramCaption("not json at all").boxes, []);
  assert.deepEqual(parseIdeogramCaption(null).boxes, []);
  assert.deepEqual(parseIdeogramCaption([1, 2]).boxes, []);
  // Element palettes capped at 5 on parse too.
  const capped = parseIdeogramCaption({
    compositional_deconstruction: { background: "", elements: [{ type: "obj", bbox: [0, 0, 100, 100], desc: "", color_palette: ["#111111", "#222222", "#333333", "#444444", "#555555", "#666666"] }] },
  });
  assert.equal(capped.boxes[0].color_palette.length, 5);
  console.log("PASS: parse accepts repaired strings, rejects garbage, caps palettes");
}

// ── 4. Legacy percent-store migration (load prefers kj, falls back) ──────

{
  localStorageStub.clear();
  localStorageStub.setItem(LEGACY_KEY, JSON.stringify({
    boxes: [{ id: "l1", kind: "object", x: 10, y: 20, w: 30, h: 40, label: "tree", color: "#ff0000" }],
    aspect: "16:9",
  }));
  const { handle } = mountEditor(undefined);
  const b = handle.getDraft().boxes[0];
  approx(b.x, 0.1); approx(b.y, 0.2); approx(b.w, 0.3); approx(b.h, 0.4);
  assert.equal(b.type, "obj");
  assert.equal(b.desc, "tree");
  assert.deepEqual(b.color_palette, ["#FF0000"]);
  handle.destroy();
  console.log("PASS: legacy percent draft migrates to fractions (kind/label/color mapped)");
}

{
  localStorageStub.clear();
  localStorageStub.setItem(KJ_KEY, JSON.stringify({
    boxes: [{ id: "k1", type: "obj", x: 0.5, y: 0.5, w: 0.2, h: 0.2, desc: "kj", color_palette: [] }],
  }));
  localStorageStub.setItem(LEGACY_KEY, JSON.stringify({
    boxes: [{ id: "l1", type: "obj", x: 0.1, y: 0.1, w: 0.1, h: 0.1, desc: "legacy", color_palette: [] }],
  }));
  const { handle } = mountEditor(undefined);
  assert.equal(handle.getDraft().boxes[0].desc, "kj");
  handle.destroy();
  console.log("PASS: kj store wins over legacy fallback");
}

{
  localStorageStub.clear();
  localStorageStub.setItem(KJ_KEY, "%%%corrupted%%%");
  localStorageStub.setItem(LEGACY_KEY, JSON.stringify({
    boxes: [{ id: "l1", type: "obj", x: 0.2, y: 0.2, w: 0.2, h: 0.2, desc: "legacy", color_palette: [] }],
  }));
  const { handle } = mountEditor(undefined);
  assert.equal(handle.getDraft().boxes[0].desc, "legacy");
  handle.destroy();
  localStorageStub.clear();
  localStorageStub.setItem(KJ_KEY, "%%%corrupted%%%");
  const { handle: blank } = mountEditor(undefined);
  assert.deepEqual(blank.getDraft().boxes, []);
  assert.equal(blank.getDraft().width, 1024);
  blank.destroy();
  console.log("PASS: corrupted kj falls back to legacy, then to blank defaults");
}

// ── 5. Persistence: save writes kj only; reload restores ──────────────────

{
  localStorageStub.clear();
  const first = mountEditor({});
  assert.equal(first.changes.length, 0, "mount alone must not emit draft changes");
  await fire(canvasOf(first.container), "pointerdown", { button: 0, clientX: 30, clientY: 30, pointerId: 1, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false });
  await pointerMove(first.container, 90, 60);
  await pointerUp(first.container, 90, 60);
  assert.equal(first.handle.getDraft().boxes.length, 1);
  assert.ok(first.changes.length >= 1, "draw commits via onDraftChange");
  const saved = JSON.parse(localStorageStub.getItem(KJ_KEY));
  assert.equal(saved.boxes.length, 1);
  assert.equal(localStorageStub.getItem(LEGACY_KEY), null, "legacy key is read-only fallback, never written");
  const second = mountEditor(undefined);
  assert.equal(second.handle.getDraft().boxes.length, 1);
  assert.equal(second.handle.getDraft().boxes[0].id, first.handle.getDraft().boxes[0].id);
  first.handle.destroy();
  second.handle.destroy();
  console.log("PASS: persistence writes kj only and reload restores the draft");
}

// ── 6. Canvas draw / select / move / resize ───────────────────────────────

{
  localStorageStub.clear();
  const { container, handle } = mountEditor({});
  // Draw on empty canvas: fractions follow the 300px stub rect.
  await pointerDown(container, 30, 30);
  await pointerMove(container, 90, 60);
  await pointerUp(container, 90, 60);
  assert.equal(handle.getDraft().boxes.length, 1);
  const drawn = handle.getDraft().boxes[0];
  approx(drawn.x, 0.1); approx(drawn.y, 0.1); approx(drawn.w, 0.2); approx(drawn.h, 0.1);
  assert.equal(activeRowIndex(container), 0, "drawn box is selected");
  // Click without dragging keeps the selection on the same box.
  await pointerDown(container, 45, 45);
  await pointerUp(container, 45, 45);
  assert.equal(handle.getDraft().boxes.length, 1);
  assert.equal(activeRowIndex(container), 0);
  // Move: drag the body by (+30,+30)px = (+0.1,+0.1).
  await pointerDown(container, 45, 45);
  await pointerMove(container, 75, 75);
  await pointerUp(container, 75, 75);
  const moved = handle.getDraft().boxes[0];
  approx(moved.x, 0.2); approx(moved.y, 0.2); approx(moved.w, 0.2); approx(moved.h, 0.1);
  // Resize: SE handle of the moved box sits at (120,90)px; drag to (150,120).
  await pointerDown(container, 120, 90);
  await pointerMove(container, 150, 120);
  await pointerUp(container, 150, 120);
  const resized = handle.getDraft().boxes[0];
  approx(resized.x, 0.2); approx(resized.y, 0.2); approx(resized.w, 0.3); approx(resized.h, 0.2);
  // Click-sized drags commit nothing and clear the selection.
  await pointerDown(container, 250, 250);
  await pointerUp(container, 250, 250);
  assert.equal(handle.getDraft().boxes.length, 1);
  handle.destroy();
  console.log("PASS: canvas draw/select/move/resize follow pointer fractions");
}

// ── 7. Overlap Alt-cycle + keyboard delete/duplicate ──────────────────────

{
  localStorageStub.clear();
  const { container, handle } = mountEditor({});
  handle.setDraft({
    boxes: [
      { x: 0.1, y: 0.1, w: 0.4, h: 0.4, type: "obj", desc: "back", color_palette: [] },
      { x: 0.2, y: 0.2, w: 0.4, h: 0.4, type: "obj", desc: "front", color_palette: [] },
    ],
  });
  // setDraft selects box 0, which the front-first list shows as the second row.
  assert.equal(activeRowIndex(container), 1);
  // Plain click in the overlap selects the front (last) box: first list row active.
  await pointerDown(container, 90, 90);
  await pointerUp(container, 90, 90);
  assert.equal(activeRowIndex(container), 0);
  // Alt-click cycles to the box underneath: second list row active.
  await pointerDown(container, 90, 90, { altKey: true });
  await pointerUp(container, 90, 90);
  assert.equal(activeRowIndex(container), 1);
  // Delete removes the selected (back) box; the front box survives.
  await canvasKey(container, "Delete");
  assert.equal(handle.getDraft().boxes.length, 1);
  assert.equal(handle.getDraft().boxes[0].desc, "front");
  // Ctrl+D duplicates with a fresh id and a small offset.
  const before = handle.getDraft().boxes[0];
  await canvasKey(container, "d", { ctrlKey: true });
  const after = handle.getDraft().boxes;
  assert.equal(after.length, 2);
  assert.notEqual(after[1].id, before.id);
  assert.equal(after[1].desc, "front");
  assert.ok(after[1].x > before.x && after[1].y > before.y, "paste offsets the duplicate");
  handle.destroy();
  console.log("PASS: Alt-click cycles overlap; Delete/Ctrl+D work on the selection");
}

// ── 8. Element editor: object/text switch, exact text, placed, palettes ───

{
  localStorageStub.clear();
  const { container, handle } = mountEditor({
    boxes: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.2, type: "obj", desc: "", text: "", color_palette: [] }],
  });
  const inSide = (n) => {
    let p = n.parentNode;
    while (p) {
      if ((p.className || "").split(" ").includes("stlay-side")) return true;
      p = p.parentNode;
    }
    return false;
  };
  const resync = async () => {
    // Row click carries no box closure (index + full touch), so it refreshes
    // the side panel with current closures. See the stale-closure note below.
    const row = q(container, (n) => n.tagName === "DIV" && hasClass(n, "stlay-lrow"));
    await fire(row, "click");
  };
  // Object elements carry no text key.
  assert.ok(!("text" in handle.getJSON().compositional_deconstruction.elements[0]));
  // Switch to text on a fresh panel (full touch): text key appears.
  const typeSel = q(container, (n) => n.tagName === "SELECT" && inSide(n));
  typeSel.value = "text";
  await fire(typeSel, "change");
  assert.equal(handle.getDraft().boxes[0].type, "text");
  // Exact text is preserved verbatim (single input event on a fresh control).
  const textInput = q(container, (n) => n.placeholder === "text (text elements only)");
  textInput.value = "SALE NOW";
  await fire(textInput, "input");
  assert.equal(handle.getJSON().compositional_deconstruction.elements[0].text, "SALE NOW");
  // Touch normalizes the draft in place (same object identity), so repeated
  // input events on the same rendered control keep landing: keystrokes
  // accumulate exactly like upstream KJNodes typing.
  textInput.value = "SALE NOW X";
  await fire(textInput, "input");
  assert.equal(
    handle.getJSON().compositional_deconstruction.elements[0].text,
    "SALE NOW X",
    "repeated input on the same control accumulates (in-place touch)"
  );
  await resync();
  // desc typing lands in the draft and the JSON preview.
  const descArea = q(container, (n) => n.placeholder === "desc (always emitted)");
  descArea.value = "lighthouse";
  await fire(descArea, "input");
  assert.equal(handle.getDraft().boxes[0].desc, "lighthouse");
  const pre = q(container, (n) => n.tagName === "PRE" && hasClass(n, "stlay-pre"));
  assert.ok(pre.textContent.includes("lighthouse"));
  await resync();
  // Unplaced checkbox omits bbox; re-placing restores it.
  const placedChk = q(container, (n) => n.tagName === "INPUT" && n.type === "checkbox");
  placedChk.checked = false;
  await fire(placedChk, "change");
  assert.ok(!("bbox" in handle.getJSON().compositional_deconstruction.elements[0]));
  const placedChk2 = q(container, (n) => n.tagName === "INPUT" && n.type === "checkbox");
  placedChk2.checked = true;
  await fire(placedChk2, "change");
  assert.ok("bbox" in handle.getJSON().compositional_deconstruction.elements[0]);
  await resync();
  // Element "+" swatch adds the default color when the clipboard is empty.
  const addBtn = q(container, (n) => n.tagName === "BUTTON" && inSide(n) && (n.title || "").startsWith("Add a color"));
  await fire(addBtn, "click");
  assert.deepEqual(handle.getDraft().boxes[0].color_palette, ["#FFFFFF"]);
  // setDraft caps element palettes at 5 uppercased entries.
  handle.setDraft({ boxes: [{ x: 0, y: 0, w: 0.1, h: 0.1, type: "obj", desc: "", color_palette: ["#111111", "#222222", "#333333", "#444444", "#555555", "#666666"] }] });
  assert.deepEqual(handle.getDraft().boxes[0].color_palette, ["#111111", "#222222", "#333333", "#444444", "#555555"]);
  handle.destroy();
  console.log("PASS: element editor switch/text/placed/palette rules");
}

// ── 9. bbox px + 0-1000 grid sync ──────────────────────────────────────────

{
  localStorageStub.clear();
  const { container, handle } = mountEditor({
    boxes: [{ x: 0.1, y: 0.2, w: 0.3, h: 0.4, type: "obj", desc: "", color_palette: [] }],
  });
  const pxX = q(container, (n) => n.tagName === "INPUT" && n.title === "bbox x in px");
  pxX.value = "60";
  await fire(pxX, "change");
  approx(handle.getDraft().boxes[0].x, 60 / 1024);
  const gridYmin = q(container, (n) => n.tagName === "INPUT" && n.title === "bbox ymin (0-1000)");
  gridYmin.value = "100";
  await fire(gridYmin, "change");
  const b = handle.getDraft().boxes[0];
  approx(b.y, 0.1);
  approx(b.h, 0.5);
  assert.deepEqual(handle.getJSON().compositional_deconstruction.elements[0].bbox[0], 100);
  handle.destroy();
  console.log("PASS: bbox px + 0-1000 grid fields sync back to fractions");
}

// ── 10. Globals, JSON preview parity, dims, import/templates ───────────────

{
  localStorageStub.clear();
  const { container, handle, changes } = mountEditor({});
  const hld = q(container, (n) => n.placeholder === "High-level description (optional, blank = omitted)");
  hld.value = "epic vista";
  await fire(hld, "input");
  const modeSel = q(container, (n) => n.tagName === "SELECT" && (n.children || []).some((o) => o && o.value === "photo"));
  modeSel.value = "photo";
  await fire(modeSel, "change");
  const bg = q(container, (n) => n.placeholder === "Background description (required scene background)");
  bg.value = "city dusk";
  await fire(bg, "input");
  const json = handle.getJSON();
  assert.equal(json.high_level_description, "epic vista");
  assert.ok(json.style_description && "photo" in json.style_description);
  assert.equal(json.compositional_deconstruction.background, "city dusk");
  // JSON preview shows exactly what getJSON returns.
  const pre = q(container, (n) => n.tagName === "PRE" && hasClass(n, "stlay-pre"));
  assert.deepEqual(JSON.parse(pre.textContent), json);
  // onDraftChange carries (draft, built) with matching text.
  const last = changes[changes.length - 1];
  assert.equal(last.built.text, JSON.stringify(json));
  // Canvas dims snap to multiples of 16 with a 64px floor.
  const wInput = q(container, (n) => n.tagName === "INPUT" && n.title === "Canvas width (multiples of 16)");
  wInput.value = "100";
  await fire(wInput, "change");
  assert.equal(handle.getDraft().width, 96);
  wInput.value = "10";
  await fire(wInput, "change");
  assert.equal(handle.getDraft().width, 64);
  // Style palette caps at 16 through setDraft.
  handle.setDraft({ color_palette: Array.from({ length: 20 }, () => "#aabbcc") });
  assert.equal(handle.getDraft().color_palette.length, 16);
  handle.destroy();
  console.log("PASS: globals + JSON preview parity + dim snapping + style cap");
}

{
  localStorageStub.clear();
  const { container, handle } = mountEditor({ boxes: [{ x: 0.1, y: 0.1, w: 0.2, h: 0.2, type: "obj", desc: "keep", color_palette: [] }] });
  // Import replaces the draft from caption JSON (dims preserved).
  const impArea = q(container, (n) => n.placeholder === "Paste an Ideogram caption JSON…");
  impArea.value = JSON.stringify({
    high_level_description: "imported",
    compositional_deconstruction: { background: "sea", elements: [{ type: "obj", bbox: [0, 0, 500, 500], desc: "boat" }] },
  });
  const impDetails = impArea.parentNode;
  const impLoad = q(impDetails, (n) => n.tagName === "BUTTON" && n.textContent === "Load");
  await fire(impLoad, "click");
  assert.equal(handle.getDraft().boxes.length, 1);
  assert.equal(handle.getDraft().boxes[0].desc, "boat");
  assert.equal(handle.getDraft().high_level_description, "imported");
  assert.equal(impArea.value, "");
  // Templates round-trip through localStorage.
  const tplName = q(container, (n) => n.placeholder === "template name");
  tplName.value = "t1";
  const tplRow = tplName.parentNode;
  const tplSave = q(tplRow, (n) => n.tagName === "BUTTON" && n.textContent === "Save");
  await fire(tplSave, "click");
  const clearBtn = q(container, (n) => n.tagName === "BUTTON" && n.textContent === "Clear all");
  await fire(clearBtn, "click");
  assert.equal(handle.getDraft().boxes.length, 0);
  const tplSel = q(tplRow, (n) => n.tagName === "SELECT");
  tplSel.value = "t1";
  const tplLoad = q(tplRow, (n) => n.tagName === "BUTTON" && n.textContent === "Load");
  await fire(tplLoad, "click");
  assert.equal(handle.getDraft().boxes.length, 1);
  assert.equal(handle.getDraft().boxes[0].desc, "boat");
  // destroy is teardown-safe and repeatable.
  handle.destroy();
  handle.destroy();
  console.log("PASS: caption import + localStorage templates + safe destroy");
}

// ── 11. Round-trip stability ───────────────────────────────────────────────

{
  const draft = {
    high_level_description: "epic",
    style_mode: "photo",
    aesthetics: "clean",
    lighting: "soft",
    photo: "35mm",
    medium: "digital",
    color_palette: ["#aabbcc"],
    background: "city",
    boxes: [
      { type: "obj", x: 0.1, y: 0.2, w: 0.3, h: 0.4, desc: "car", color_palette: ["#ff0000", "#00ff00"] },
      { type: "text", x: 0.3, y: 0.3, w: 0.2, h: 0.1, desc: "sign", text: "SHOP", nobbox: true, color_palette: [] },
    ],
  };
  const first = buildIdeogramCaption(draft).text;
  const reparsed = parseIdeogramCaption(JSON.parse(first));
  const second = buildIdeogramCaption(reparsed).text;
  assert.equal(second, first, "build(parse(build(d))) must be byte-stable");
  const emptyRound = buildIdeogramCaption(parseIdeogramCaption(buildIdeogramCaption({}).text)).text;
  assert.equal(emptyRound, buildIdeogramCaption({}).text);
  console.log("PASS: caption build/parse round-trip is byte-stable");
}

console.log("ALL STUDIO LAYOUT EDITOR UNIT TESTS GREEN");
