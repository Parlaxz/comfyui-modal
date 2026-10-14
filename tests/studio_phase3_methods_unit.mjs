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
  WORKFLOW_REFERENCE_METHODS,
  loadReferenceCards,
  saveReferenceCards,
  clearReferenceCards,
} from "../web/studio-playground-state.js";
import { REFERENCE_METHODS } from "../web/studio-workflow-run.js";

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
  referenceMethod: "",
  referenceOverride: "",
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

  it("exposes the frozen reference method ids (Lane A contract)", () => {
    assert.deepEqual([...WORKFLOW_REFERENCE_METHODS], [
      "conditioning_slots",
      "reference_latent_chain",
      "dedicated",
    ]);
    // Mirrors the pure-logic module: the dropdown, gates, and payload key
    // on the same ids (no Auto anywhere).
    assert.deepEqual([...REFERENCE_METHODS], [...WORKFLOW_REFERENCE_METHODS]);
    assert.ok(!WORKFLOW_REFERENCE_METHODS.includes("auto"));
  });

  it("reference method defaults to unchosen and round-trips per workflow", () => {
    assert.equal(loadWorkflowMethods("wf_1").referenceMethod, "");
    saveWorkflowMethods("wf_1", {
      referenceMethod: "conditioning_slots",
      referenceOverride: "wf_dedicated",
    });
    const loaded = loadWorkflowMethods("wf_1");
    assert.equal(loaded.referenceMethod, "conditioning_slots");
    assert.equal(loaded.referenceOverride, "wf_dedicated");
    // Switching workflows preserves each workflow's own choice.
    saveWorkflowMethods("wf_2", { referenceMethod: "dedicated", referenceOverride: "wf_d2" });
    assert.equal(loadWorkflowMethods("wf_1").referenceMethod, "conditioning_slots");
    assert.equal(loadWorkflowMethods("wf_2").referenceMethod, "dedicated");
    assert.equal(loadWorkflowMethods("wf_2").referenceOverride, "wf_d2");
  });

  it("ignores invalid reference methods and non-string overrides", () => {
    saveWorkflowMethods("wf_1", { referenceMethod: "conditioning_slots" });
    saveWorkflowMethods("wf_1", { referenceMethod: "auto", referenceOverride: 42 });
    const loaded = loadWorkflowMethods("wf_1");
    assert.equal(loaded.referenceMethod, "conditioning_slots");
    assert.equal(loaded.referenceOverride, "");
    saveWorkflowMethods("wf_1", { referenceMethod: "not_a_method" });
    assert.equal(loadWorkflowMethods("wf_1").referenceMethod, "conditioning_slots");
  });

  it("keeps a remembered reference method across reload-shaped reads", () => {
    // Reload = fresh reads from the same storage: the choice survives and
    // is never rewritten by the read path itself.
    saveWorkflowMethods("wf_1", { referenceMethod: "reference_latent_chain" });
    const before = _mem.get(METHODS_KEY);
    assert.equal(loadWorkflowMethods("wf_1").referenceMethod, "reference_latent_chain");
    assert.equal(loadWorkflowMethods("wf_1").referenceMethod, "reference_latent_chain");
    assert.equal(_mem.get(METHODS_KEY), before);
  });
});

describe("studio phase-8 reference cards", () => {
  beforeEach(() => {
    _mem.clear();
  });

  it("loads empty for unknown workflow+version", () => {
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), []);
  });

  it("ignores invalid workflow ids", () => {
    for (const bad of ["", null, undefined, 0, 123, {}, []]) {
      assert.deepEqual(loadReferenceCards(bad, "wv_1"), []);
      saveReferenceCards(bad, "wv_1", [{ id: "a", file: "x.png", label: "" }]);
    }
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), []);
  });

  it("round-trips ordered cards per workflow+version", () => {
    const cards = [
      { id: "ref_a", file: "a.png", label: "" },
      { id: "ref_b", file: "b.png", label: "Logo" },
    ];
    saveReferenceCards("wf_1", "wv_1", cards);
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), cards);
    // Order is the submitted order: re-saving reordered stays reordered.
    saveReferenceCards("wf_1", "wv_1", [cards[1], cards[0]]);
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), [cards[1], cards[0]]);
  });

  it("isolates versions and workflows (switches preserve correct state)", () => {
    saveReferenceCards("wf_1", "wv_1", [{ id: "a", file: "a.png", label: "" }]);
    saveReferenceCards("wf_1", "wv_2", [{ id: "b", file: "b.png", label: "" }]);
    saveReferenceCards("wf_2", "wv_1", [{ id: "c", file: "c.png", label: "" }]);
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), [{ id: "a", file: "a.png", label: "" }]);
    assert.deepEqual(loadReferenceCards("wf_1", "wv_2"), [{ id: "b", file: "b.png", label: "" }]);
    assert.deepEqual(loadReferenceCards("wf_2", "wv_1"), [{ id: "c", file: "c.png", label: "" }]);
    // Clearing one version leaves the others alone.
    clearReferenceCards("wf_1", "wv_1");
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), []);
    assert.deepEqual(loadReferenceCards("wf_1", "wv_2"), [{ id: "b", file: "b.png", label: "" }]);
  });

  it("drops malformed cards and recovers on malformed JSON", () => {
    saveReferenceCards("wf_1", "wv_1", [
      { id: "ok", file: "ok.png", label: "x" },
      null,
      "nope",
      42,
      { id: "nofile" },
    ]);
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), [
      { id: "ok", file: "ok.png", label: "x" },
      { id: "nofile", file: "", label: "" },
    ]);
    _mem.set("comfymodal.studio.references.v1", "{oops-not-json");
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), []);
    _mem.set("comfymodal.studio.references.v1", "[1,2,3]");
    assert.deepEqual(loadReferenceCards("wf_1", "wv_1"), []);
  });
});
