// Modal Studio — Phase-3 per-workflow method preferences unit tests.
//
// Executable behavioral tests that import and run the actual persistence
// helpers (web/studio-playground-state.js) with an in-memory localStorage
// stub. No browser, no DOM, plain Node.
//
// The module reads localStorage lazily inside functions, so installing the
// stub before the first load/save call is sufficient.
//
// Run: node --test tests/studio_phase3_methods_unit.mjs

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  loadWorkflowMethods,
  saveWorkflowMethods,
} from "../web/studio-playground-state.js";

const METHODS_KEY = "comfymodal.studio.methods.v1";

const _mem = new Map();
globalThis.localStorage = {
  getItem: (key) => (_mem.has(String(key)) ? _mem.get(String(key)) : null),
  setItem: (key, value) => {
    _mem.set(String(key), String(value));
  },
  removeItem: (key) => {
    _mem.delete(String(key));
  },
  clear: () => {
    _mem.clear();
  },
};

const DEFAULTS = {
  inpaintMethod: "crop_stitch",
  inpaintOverride: "",
  expandMethod: "pad_preserve",
  expandOverride: "",
  padTop: 0,
  padRight: 256,
  padBottom: 0,
  padLeft: 0,
  savedMask: "",
  savedMaskSource: "",
};

describe("studio phase-3 workflow method preferences", () => {
  beforeEach(() => {
    _mem.clear();
  });

  it("returns defaults for unknown workflow ids", () => {
    assert.deepEqual(loadWorkflowMethods("wf_never_saved"), DEFAULTS);
  });

  it("ignores invalid workflow ids", () => {
    for (const bad of ["", null, undefined, 0, 123, {}, []]) {
      assert.deepEqual(loadWorkflowMethods(bad), DEFAULTS);
    }
  });

  it("merge-patches known keys and keeps other defaults", () => {
    saveWorkflowMethods("wf_1", { inpaintMethod: "conditioning", padTop: 12 });
    assert.deepEqual(loadWorkflowMethods("wf_1"), { ...DEFAULTS, inpaintMethod: "conditioning", padTop: 12 });
    // A second patch merges onto the stored entry, not onto defaults.
    saveWorkflowMethods("wf_1", { expandMethod: "pad" });
    assert.deepEqual(loadWorkflowMethods("wf_1"), {
      ...DEFAULTS,
      inpaintMethod: "conditioning",
      padTop: 12,
      expandMethod: "pad",
    });
  });

  it("ignores unknown keys and invalid values in patches", () => {
    saveWorkflowMethods("wf_1", {
      bogusKey: "nope",
      inpaintMethod: "not_a_method",
      expandMethod: 42,
      padTop: "not_a_number",
    });
    const loaded = loadWorkflowMethods("wf_1");
    assert.deepEqual(loaded, DEFAULTS);
    assert.ok(!("bogusKey" in loaded));
  });

  it("ignores saves with invalid workflow ids", () => {
    for (const bad of ["", null, undefined, 0]) {
      saveWorkflowMethods(bad, { inpaintMethod: "conditioning" });
    }
    assert.equal(_mem.get(METHODS_KEY), undefined);
    assert.deepEqual(loadWorkflowMethods("wf_1"), DEFAULTS);
  });

  it("round-trips savedMask/savedMaskSource", () => {
    saveWorkflowMethods("wf_1", { savedMask: "mask_abc.png", savedMaskSource: "src_xyz.png" });
    const loaded = loadWorkflowMethods("wf_1");
    assert.equal(loaded.savedMask, "mask_abc.png");
    assert.equal(loaded.savedMaskSource, "src_xyz.png");
  });

  it("recovers to defaults on malformed JSON", () => {
    _mem.set(METHODS_KEY, "{oops-not-json");
    assert.deepEqual(loadWorkflowMethods("wf_1"), DEFAULTS);
    // Saving after corruption still works (store rebuilds from scratch).
    saveWorkflowMethods("wf_1", { inpaintMethod: "dedicated" });
    assert.equal(loadWorkflowMethods("wf_1").inpaintMethod, "dedicated");
  });

  it("recovers to defaults on non-object JSON and entries", () => {
    _mem.set(METHODS_KEY, "[1,2,3]");
    assert.deepEqual(loadWorkflowMethods("wf_1"), DEFAULTS);
    _mem.set(METHODS_KEY, JSON.stringify({ wf_1: "not-an-entry", wf_2: null }));
    assert.deepEqual(loadWorkflowMethods("wf_1"), DEFAULTS);
    assert.deepEqual(loadWorkflowMethods("wf_2"), DEFAULTS);
  });
});
