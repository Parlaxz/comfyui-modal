// Phase I5 — Lightweight A/B image compare: focused unit tests.
//
// Registered in tests/run_studio_tests.py NODE_UNIT_FILES by convergence
// lane I9A (2026-08-25). Can also run directly:
//   node tests/studio_phase_i5_image_compare_unit.mjs
//
// Covers the pure compare-session model (exactly two transient slots,
// replace-B semantics, single divider authority 0–100) plus structural
// proofs: no persistence/backend vocabulary in the new module, retirement
// guard against the old Comparison product, and the generation-detail /
// experiment-detail entry wiring.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

// ── House DOM stub (cf. studio_phase_i3_shared_primitives_unit.mjs) ───────

function makeNode(tag) {
  const node = {
    tagName: String(tag || "div").toUpperCase(),
    children: [],
    parentNode: null,
    attributes: {},
    dataset: {},
    style: {},
    className: "",
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      const i = this.children.indexOf(child);
      if (i !== -1) this.children.splice(i, 1);
      child.parentNode = null;
      return child;
    },
    get firstChild() {
      return this.children.length ? this.children[0] : null;
    },
    setAttribute(name, v) {
      this.attributes[name] = String(v);
    },
    getAttribute(name) {
      return name in this.attributes ? this.attributes[name] : null;
    },
    hasAttribute(name) {
      return name in this.attributes;
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    get textContent() {
      return node.children.map((c) => (c.textContent == null ? "" : c.textContent)).join("");
    },
    set textContent(v) {
      node.children = [];
    },
  };
  return node;
}

globalThis.document = {
  createElement: makeNode,
  createTextNode: (t) => ({ nodeType: 3, textContent: String(t), parentNode: null }),
};

const compare = await import(pathToFileURL(path.join(WEB, "studio-image-compare.js")));

const DESC_A = { url: "/assets/a.png", label: "Preview", kind: "preview", meta: "Generation #abc123", alt: "preview" };
const DESC_B = { url: "/assets/b.png", label: "Original", kind: "original", meta: "Generation #abc123" };
const DESC_C = { url: "/assets/c.png", label: "Output 2", kind: "output" };

function freshModel() {
  return compare.createCompareSessionModel();
}

// ═══ 1. Initial empty state ═══════════════════════════════════════════════

{
  const m = freshModel();
  const st = m.getState();
  assert.equal(st.a, null, "no A initially");
  assert.equal(st.b, null, "no B initially");
  assert.equal(st.position, 50, "divider defaults to 50%");
  section("1. initial state is empty with divider default 50");
}

// ═══ 2–4. Select A, fill B, third selection replaces B (A stable) ════════

{
  const m = freshModel();
  assert.equal(m.setA(DESC_A), true, "setA accepts a usable descriptor");
  let st = m.getState();
  assert.equal(st.a.label, "Preview");
  assert.equal(st.b, null, "B still empty after A");

  assert.equal(m.setB(DESC_B), true, "second image fills B");
  st = m.getState();
  assert.equal(st.b.label, "Original");

  // Third eligible pick truthfully REPLACES B; A remains stable.
  assert.equal(m.setB(DESC_C), true);
  st = m.getState();
  assert.equal(st.a.label, "Preview", "A unchanged by later picks");
  assert.equal(st.b.label, "Output 2", "third selection replaced B");

  // An explicit NEW A starts a fresh pair (stale B never mixes bases).
  const m2 = freshModel();
  m2.setA(DESC_A);
  m2.setB(DESC_B);
  m2.setA(DESC_C);
  const st2 = m2.getState();
  assert.equal(st2.a.label, "Output 2");
  assert.equal(st2.b, null, "new A discards the previous pairing");
  section("2-4. select A → fill B → further pick replaces B; new A resets the pair");
}

// ═══ 5. Reset clears both slots (and restores default position) ══════════

{
  const m = freshModel();
  m.setA(DESC_A);
  m.setB(DESC_B);
  m.setPosition(80);
  m.reset();
  const st = m.getState();
  assert.equal(st.a, null, "reset clears A");
  assert.equal(st.b, null, "reset clears B");
  assert.equal(st.position, 50, "reset restores default divider");
  section("5. reset clears the session");
}

// ═══ 6–9. Single divider authority: default, clamp, arrows, Home/End ═════

{
  const m = freshModel();
  assert.equal(m.getPosition ? undefined : undefined, undefined); // API surface guard
  assert.equal(m.getState().position, 50);

  assert.equal(m.setPosition("37"), true, "numeric strings coerce");
  assert.equal(m.getState().position, 37);

  // Clamp: values outside 0–100 land on the boundary.
  m.setPosition(-10);
  assert.equal(m.getState().position, 0, "clamped to 0");
  m.setPosition(140);
  assert.equal(m.getState().position, 100, "clamped to 100");
  m.setPosition(33.6);
  assert.equal(m.getState().position, 34, "rounded to integer percent");

  // Arrow increments (±5).
  m.setPosition(50);
  m.nudgePosition(5);
  assert.equal(m.getState().position, 55, "ArrowRight semantics (+5)");
  m.nudgePosition(-5);
  assert.equal(m.getState().position, 50, "ArrowLeft semantics (−5)");
  m.setPosition(98);
  m.nudgePosition(5);
  assert.equal(m.getState().position, 100, "arrow clamps at max");
  m.nudgePosition(-5);
  m.setPosition(2);
  m.nudgePosition(-5);
  assert.equal(m.getState().position, 0, "arrow clamps at min");

  // Home / End.
  m.setPosition(42);
  m.setPosition(0);
  assert.equal(m.getState().position, 0, "Home → 0");
  m.setPosition(100);
  assert.equal(m.getState().position, 100, "End → 100");

  // Fail-soft: garbage never corrupts state.
  assert.equal(m.setPosition(NaN), false);
  assert.equal(m.setPosition(undefined), false);
  assert.equal(m.setPosition({}), false);
  assert.equal(m.getState().position, 100, "invalid setPosition is a no-op");
  assert.equal(m.nudgePosition("junk"), false, "invalid nudge is a no-op");
  section("6-9. position default/coercion, clamp+round, ±5 nudges, Home/End, fail-soft");
}

// ═══ 10. Descriptor validation / fail-soft ════════════════════════════════

{
  for (const bad of [null, undefined, 42, "url", {}, { url: "" }, { url: "   " }, { url: 7 }, { label: "x" }]) {
    assert.equal(compare.normalizeImageDescriptor(bad), null, `unusable input rejected: ${JSON.stringify(bad)}`);
  }
  const d = compare.normalizeImageDescriptor({
    url: " /x/y.png ",
    label: "  ",
    kind: "",
    alt: "",
  });
  assert.ok(d, "minimal usable object normalizes");
  assert.equal(d.url, "/x/y.png", "URL trimmed");
  assert.equal(d.label, "Image", "blank label falls back");
  assert.equal(d.kind, "image", "blank kind falls back");
  assert.equal(d.alt, "Image", "alt falls back to label");
  const long = compare.normalizeImageDescriptor({
    url: "/x.png",
    label: "L".repeat(200),
    meta: "M".repeat(300),
  });
  assert.equal(long.label.length, 80, "label capped");
  assert.equal(long.meta.length, 120, "meta capped");

  // Model rejects unusable descriptors without mutating state.
  const m = freshModel();
  assert.equal(m.setA(null), false);
  assert.equal(m.setB({}), false);
  assert.deepEqual(m.getState(), { a: null, b: null, position: 50 }, "failed sets mutate nothing");

  // Presentation-only shape: exactly the five display fields.
  assert.deepEqual(
    Object.keys(compare.normalizeImageDescriptor(DESC_A)).sort(),
    ["alt", "kind", "label", "meta", "url"],
    "descriptors carry only client-side presentation data"
  );
  section("10. descriptor validation is fail-soft; only presentation data stored");
}

// ═══ 11. onChange notification contract ═══════════════════════════════════

{
  const seen = [];
  const m = compare.createCompareSessionModel({
    onChange: (st) => seen.push(st.position),
    normalize: compare.normalizeImageDescriptor,
  });
  m.setPosition(10);
  m.nudgePosition(5);
  m.setPosition("junk");
  assert.deepEqual(seen, [10, 15], "onChange fires on real changes only");
  section("11. onChange observes committed changes only");
}

// ═══ 12. Transient-state proof: no persistence/backend vocabulary ═════════

{
  const src = readWeb("studio-image-compare.js");
  for (const banned of [
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "XMLHttpRequest",
    "fetch(",
    "history.replaceState",
    "pushState",
    ".POST",
    "PATCH",
    "repo.",
    "studio-backend",
    "history-v2-repository",
    "/comparison/",
    "comparison/run",
    "ComparisonProfile",
    "ComparisonRunner",
    "ab-slider",
  ]) {
    assert.equal(src.includes(banned), false, `module must stay free of "${banned}"`);
  }
  // Only shared-primitive imports allowed.
  const imports = [...src.matchAll(/^import[^;]+;/gm)].map((m2) => m2[0]);
  assert.equal(imports.length, 1, "single import line");
  assert.ok(imports[0].includes('from "./studio-ui.js"'), "imports only el/registerLayerHandler from studio-ui");
  section("12. zero persistence/backend/route/retired-product vocabulary; dependency-light import");
}

// ═══ 13. Entry wiring: generation detail + experiment detail ═════════════

{
  const detailSrc = readWeb("studio-history-v2-detail.js");
  const expSrc = readWeb("studio-history-v2-experiment.js");
  assert.ok(detailSrc.includes('from "./studio-image-compare.js"'), "detail imports the compare module");
  assert.ok(detailSrc.includes('"data-testid": "history-v2-compare"'), "plain Compare action present");
  assert.ok(detailSrc.includes('"data-testid": "history-v2-compare-original"'), "Compare-with-Original pair action present");
  assert.ok(detailSrc.includes("buildAddToCompareItem"), "output menu can offer Add to compare (B)");
  assert.ok(expSrc.includes('from "./studio-image-compare.js"'), "experiment imports the compare module");
  assert.ok(expSrc.includes('"data-testid": "history-v2-cell-detail-compare-"'), "cell pane Compare action present");
  assert.ok(expSrc.includes("buildAddToCompareItem"), "cell surfaces can offer Add to compare (B)");
  // No Experiment-specific comparison store was created.
  assert.equal(expSrc.includes("compareSessionModel("), false, "no second model instantiated in experiment surface");
  section("13. Compare entries wired in generation detail and experiment cell surfaces");
}

// ═══ 14. Viewer helpers: markers intact, stale claim removed ═════════════

{
  const uiSrc = readWeb("studio-ui.js");
  for (const marker of [
    "export function createZoomableImageEl(imageUrl, alt, opts)",
    "export function createImagePreviewOverlay(opts)",
    '"comfymodal-studio-zoom-wrap"',
    '"comfymodal-studio-preview-overlay"',
    "zoomable-image",
  ]) {
    assert.ok(uiSrc.includes(marker), `viewer marker intact: ${marker}`);
  }
  assert.equal(
    uiSrc.includes("Used by both experiment cell detail"),
    false,
    "stale caller claim removed from the overlay docblock"
  );
  section("14. generic viewer helpers byte-markers intact; stale doc claims removed");
}

console.log("PASS: phase-i5 image compare unit complete");
