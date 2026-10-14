// Modal Studio — Phase-6 sketch contract tests (static).
//
// Zero-dependency Node tests that pin the Phase-6 Sketch surface without a
// browser: the engine/layers/panels modules are classic IIFE scripts (window
// globals, NOT node-importable) and the shell is ESM with a dynamic import,
// so this spec reads the sources as text and asserts on stable tokens.
//
// Covers: four web/studio-sketch-*.js modules exist with their factory fns,
// engine MIT attribution + 8 tools + composite/history/zoom tokens, layer
// store ops + base protection, shell upload/commit contract with no new
// workflow-type/provenance keys, playground sketch routing with the legacy
// inpaint/Select path unchanged, legacy sketch testids + save text, and
// no generic registry/plugin-framework or ComfyUI-node tokens in new code.
//
// Run: node --test tests/studio_phase6_sketch_contract.mjs

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.join(HERE, "..", "web");

function read(name) {
  return fs.readFileSync(path.join(WEB, name), "utf8");
}

function has(src, token) {
  return src.includes(token);
}

function hasAll(src, tokens) {
  return tokens.filter((t) => !src.includes(t));
}

function hasNone(src, tokens) {
  return tokens.filter((t) => src.includes(t));
}

// Strip line/block comments so the overengineering pin (item 6) asserts on
// real code, not prose. The engine header documents the OMITTED upstream
// wiring ("Replaced/omitted: ... app.registerExtension + LiteGraph ...,
// canvasDataWidget ..."), which must not trip the pin.
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^\s:"'`])\/\/.*$/gm, "$1");
}

const SKETCH_FILES = [
  "studio-sketch-engine.js",
  "studio-sketch-layers.js",
  "studio-sketch-panels.js",
  "studio-sketch-shell.js",
];

describe("studio phase-6 sketch contract", () => {
  it("all four sketch modules exist with their factory fns", () => {
    for (const f of SKETCH_FILES) {
      assert.ok(fs.existsSync(path.join(WEB, f)), `missing web/${f}`);
    }
    assert.ok(has(read("studio-sketch-engine.js"), "function createSketchEngine("));
    assert.ok(has(read("studio-sketch-layers.js"), "function createLayerStore("));
    assert.ok(has(read("studio-sketch-panels.js"), "function mountSketchPanels("));
    const shell = read("studio-sketch-shell.js");
    assert.ok(has(shell, "export function openSketch("));
    assert.ok(!has(shell, "wireSketchIntoPlayground"), "dead wiring stub must stay deleted");
  });

  it("engine has MIT attribution, 8 tools, composite, history, zoom/fit", () => {
    const src = read("studio-sketch-engine.js");
    // MIT attribution: upstream repo + author.
    assert.ok(has(src, "comfysketch"), "missing comfysketch attribution");
    assert.ok(has(src, "Vitor Silva"), "missing Vitor Silva attribution");
    assert.ok(
      has(src, "https://github.com/Mexes1978/comfyui-comfysketch"),
      "missing upstream URL attribution",
    );
    // All 8 tools.
    const missing = hasAll(
      src,
      ["brush", "pencil", "eraser", "line", "rectangle", "circle", "fill", "eyedropper"].map(
        (t) => `"${t}"`,
      ),
    );
    assert.deepEqual(missing, [], `engine missing tools: ${missing.join(", ")}`);
    // Composite + fill + history + zoom/fit tokens.
    const missingCore = hasAll(src, [
      "renderLayers",
      "floodFill",
      "function undo(",
      "function redo(",
      "adjustZoom",
      "zoomIn",
      "zoomOut",
      "function fit(",
    ]);
    assert.deepEqual(missingCore, [], `engine missing core tokens: ${missingCore.join(", ")}`);
  });

  it("layers file has CRUD/visibility/opacity/reorder/duplicate/merge/flatten + base protection", () => {
    const src = read("studio-sketch-layers.js");
    const missing = hasAll(src, [
      "add:",
      "delete:",
      "rename:",
      "setVisibility",
      "setOpacity",
      "reorder",
      "duplicate",
      "mergeDown",
      "flatten",
    ]);
    assert.deepEqual(missing, [], `layers missing ops: ${missing.join(", ")}`);
    assert.ok(has(src, "toggleVisibility"), "missing visibility toggle");
    // Base protection: index-0 locked base entry that cannot move/delete.
    const missingBase = hasAll(src, ["BASE_ID", "isBase", "locked"]);
    assert.deepEqual(missingBase, [], `layers missing base protection: ${missingBase.join(", ")}`);
  });

  it("shell uploads via uploadImageBlob/uniqueImageName('studio-sketch') with source_image commit hook", () => {
    const src = read("studio-sketch-shell.js");
    assert.ok(has(src, "uploadImageBlob"), "missing uploadImageBlob");
    assert.ok(
      has(src, 'uniqueImageName("studio-sketch")'),
      "missing uniqueImageName(\"studio-sketch\")",
    );
    assert.ok(has(src, "onCommitted"), "missing onCommitted commit hook");
    assert.ok(has(src, "source_image"), "missing source_image commit target");
    assert.ok(has(src, "flattenToBlob"), "missing flattenToBlob engine contract");
    // NO new workflow-type/provenance keys. Key-shaped patterns only: the
    // file documents their deliberate absence in prose ("provenance keys"),
    // which must not trip this pin.
    const banned = hasNone(src, [
      "workflow_type",
      "workflowType",
      "workflow-type",
      "provenance:",
      '"provenance"',
      "'provenance'",
      "sketch_workflow",
      "sketchWorkflow",
      "execution_method",
      "executionMethod",
    ]);
    assert.deepEqual(banned, [], `shell has new workflow/provenance keys: ${banned.join(", ")}`);
  });

  it("playground: sketch routes to _renderSketchEditor, inpaint/Select keep _renderPaintEditor", () => {
    const src = read("studio-playground.js");
    assert.ok(has(src, "function _renderSketchEditor("), "missing _renderSketchEditor");
    assert.ok(
      has(src, 'if (tool === "sketch")'),
      "missing sketch branch in _renderToolEditor",
    );
    assert.ok(
      has(src, "return _renderSketchEditor(state, context, actions, canvasEl)"),
      "sketch branch does not call _renderSketchEditor",
    );
    // Inpaint regression pin: dedicated branch unchanged.
    assert.ok(
      has(src, 'if (tool === "inpaint") return _renderPaintEditor(state, tool, context, actions, canvasEl)'),
      "inpaint branch changed — painter regression",
    );
    // Select-on-I2I regression pin: keeps the stable "inpaint" id.
    assert.ok(
      has(src, 'return _renderPaintEditor(state, "inpaint", context, actions, canvasEl)'),
      "Select-on-I2I branch changed — painter regression",
    );
    assert.ok(
      has(src, "function _renderPaintEditor(state, tool, context, actions, canvasEl)"),
      "_renderPaintEditor signature changed",
    );
    assert.ok(has(src, "fallbackToLegacy"), "missing fallbackToLegacy");
    // Legacy testids (paint-editor dynamic `tool + "-…"` ids cover
    // sketch-canvas-wrap/sketch-canvas/sketch-undo/sketch-save; the Phase-6
    // _renderSketchEditor adds literal sketch-editor/sketch-mask-preview).
    const combined = SKETCH_FILES.map(read).join("\n") + "\n" + src;
    const missingIds = hasAll(combined, [
      "sketch-editor",
      "sketch-canvas-wrap",
      "sketch-canvas",
      "sketch-undo",
      "sketch-save",
      "sketch-mask-preview",
    ]);
    assert.deepEqual(missingIds, [], `missing legacy testids: ${missingIds.join(", ")}`);
    assert.ok(
      has(src, "Sketch saved as Source Image"),
      "missing legacy save text 'Sketch saved as Source Image'",
    );
    // NO generic registry/plugin-framework tokens in the new modules
    // (exact camelCase tokens only — prose use of "registry" is allowed).
    for (const f of SKETCH_FILES) {
      const bad = hasNone(read(f), [
        "registerPlugin",
        "pluginRegistry",
        "toolRegistry",
        "adapterFramework",
      ]);
      assert.deepEqual(bad, [], `${f} has registry/framework tokens: ${bad.join(", ")}`);
    }
  });

  it("new modules have no ComfyUI-node wiring tokens in code", () => {
    for (const f of SKETCH_FILES) {
      const code = stripComments(read(f));
      const bad = hasNone(code, ["app.registerExtension", "LiteGraph", "canvasDataWidget"]);
      assert.deepEqual(bad, [], `${f} has node-wiring tokens: ${bad.join(", ")}`);
    }
  });
});
