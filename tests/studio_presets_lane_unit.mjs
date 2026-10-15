// Modal Studio — Phase 12 preset lane unit tests.
//
// Executable behavioral tests for the preset frontend glue (all DOM-free):
//   web/studio-backend-api.js  preset client (paths, methods, normalization)
//   web/studio-playground-state.js  activePresetId + revision-keyed drafts
//   web/studio-workflow-run.js  exact-version overrides + output options
//   owner hooks: layout / guidance / sketch-shell / postprocess / output
//
// Section shapes mirror the backend contract (studio_domain/preset_state.py
// — the server stays the authority).
//
// No browser, no DOM, plain Node. fetch + localStorage are shimmed below.
//
// Run: node --test tests/studio_presets_lane_unit.mjs

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// ── Shims (modules read these lazily; define before first call) ──────────

const _lsStore = new Map();
globalThis.localStorage = {
  getItem: (k) => (_lsStore.has(String(k)) ? _lsStore.get(String(k)) : null),
  setItem: (k, v) => { _lsStore.set(String(k), String(v)); },
  removeItem: (k) => { _lsStore.delete(String(k)); },
};

const fetchCalls = [];
let fetchHandler = null;
globalThis.fetch = async (url, options) => {
  fetchCalls.push({ url: String(url), options: options || {} });
  if (typeof fetchHandler === "function") return fetchHandler(String(url), options || {});
  return { ok: true, status: 200, json: async () => ({ status: "ok" }) };
};

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB_DIR = join(HERE, "..", "web");
const SHA64 = "a".repeat(64);

import {
  versionPresetsEndpointPath,
  presetEndpointPath,
  presetDuplicateEndpointPath,
  presetCopyToVersionEndpointPath,
  listVersionPresets,
  createVersionPreset,
  getPreset,
  updatePreset,
  deletePreset,
  duplicatePreset,
  copyPresetToVersion,
  normalizePresetList,
  normalizePresetRecord,
} from "../web/studio-backend-api.js";

import {
  saveActivePreset,
  loadActivePreset,
  clearActivePreset,
  savePresetWorkingDraft,
  loadPresetWorkingDraft,
  clearPresetWorkingDraft,
} from "../web/studio-playground-state.js";

import {
  createWorkflowRunStore,
  applyPresetCoreOverrides,
  resolveEffectiveOutputOptions,
} from "../web/studio-workflow-run.js";

import {
  snapshotGuidanceForPreset,
  applyGuidanceFromPreset,
  resetGuidanceForPreset,
} from "../web/studio-guidance.js";

import {
  openSketch,
  snapshotSketchSettingsForPreset,
  applySketchSettingsFromPreset,
  resetSketchForPreset,
  clearSketchBaseForPreset,
} from "../web/studio-sketch-shell.js";

import {
  snapshotLayoutForPreset,
  applyLayoutFromPreset,
  resetLayoutForPreset,
} from "../web/studio-layout-editor.js";

import {
  defaultRecipe,
  snapshotPostRecipeForPreset,
  mergePostRecipeForPreset,
  neutralPostRecipeForPreset,
  applyPostRecipeForPreset,
  clearPostPresetPending,
} from "../web/studio-postprocess.js";

import { buildPresetOutputOverride } from "../web/studio-output-preferences.js";

beforeEach(() => {
  _lsStore.clear();
  fetchCalls.length = 0;
  fetchHandler = null;
  clearPostPresetPending();
});

// ── Preset client: paths + methods ────────────────────────────────────────

describe("preset client paths", () => {
  it("builds the contract REST paths", () => {
    assert.equal(versionPresetsEndpointPath("v1"), "/studio/workflows/versions/v1/presets");
    assert.equal(presetEndpointPath("p1"), "/studio/workflows/presets/p1");
    assert.equal(presetDuplicateEndpointPath("p1"), "/studio/workflows/presets/p1/duplicate");
    assert.equal(
      presetCopyToVersionEndpointPath("p1"),
      "/studio/workflows/presets/p1/copy-to-version"
    );
  });

  it("encodes ids in paths", () => {
    assert.ok(presetEndpointPath("a/b").includes("a%2Fb"));
  });
});

describe("preset client methods", () => {
  it("lists version presets with GET", async () => {
    fetchHandler = async () => ({ ok: true, status: 200, json: async () => ({ status: "ok", presets: [] }) });
    const res = await listVersionPresets("/comfymodal", "v1");
    assert.equal(fetchCalls.length, 1);
    assert.equal(fetchCalls[0].url, "/comfymodal/studio/workflows/versions/v1/presets");
    assert.ok(!fetchCalls[0].options.method || fetchCalls[0].options.method === undefined);
    assert.deepEqual(res, { status: "ok", presets: [] });
  });

  it("creates with POST + JSON body", async () => {
    const payload = { name: "n", studio_state: { schema_version: 1 } };
    await createVersionPreset("/comfymodal", "v1", payload);
    assert.equal(fetchCalls[0].url, "/comfymodal/studio/workflows/versions/v1/presets");
    assert.equal(fetchCalls[0].options.method, "POST");
    assert.deepEqual(JSON.parse(fetchCalls[0].options.body), payload);
  });

  it("gets/patches/deletes one preset", async () => {
    await getPreset("/comfymodal", "p1");
    assert.equal(fetchCalls[0].url, "/comfymodal/studio/workflows/presets/p1");
    await updatePreset("/comfymodal", "p1", { name: "x" });
    assert.equal(fetchCalls[1].options.method, "PATCH");
    assert.deepEqual(JSON.parse(fetchCalls[1].options.body), { name: "x" });
    await deletePreset("/comfymodal", "p1");
    assert.equal(fetchCalls[2].options.method, "DELETE");
  });

  it("duplicates and copy-forwards with POST", async () => {
    await duplicatePreset("/comfymodal", "p1", { name: "copy" });
    assert.equal(fetchCalls[0].url, "/comfymodal/studio/workflows/presets/p1/duplicate");
    assert.equal(fetchCalls[0].options.method, "POST");
    await copyPresetToVersion("/comfymodal", "p1", { workflow_version_id: "v2" });
    assert.equal(fetchCalls[1].url, "/comfymodal/studio/workflows/presets/p1/copy-to-version");
    assert.equal(fetchCalls[1].options.method, "POST");
    assert.deepEqual(JSON.parse(fetchCalls[1].options.body), { workflow_version_id: "v2" });
  });

  it("returns null for missing ids without fetching", async () => {
    assert.equal(await listVersionPresets("/comfymodal", ""), null);
    assert.equal(await getPreset("/comfymodal", ""), null);
    assert.equal(await updatePreset("/comfymodal", "", {}), null);
    assert.equal(await deletePreset("/comfymodal", ""), null);
    assert.equal(await duplicatePreset("/comfymodal", "", {}), null);
    assert.equal(await copyPresetToVersion("/comfymodal", "", {}), null);
    assert.equal(fetchCalls.length, 0);
  });

  it("normalizes list/record envelopes, degrading malformed to empty/null", () => {
    const rec = { preset_id: "p1", name: "n" };
    assert.deepEqual(normalizePresetList({ presets: [rec, null, 42] }), [rec]);
    assert.deepEqual(normalizePresetList(null), []);
    assert.deepEqual(normalizePresetList({}), []);
    assert.deepEqual(normalizePresetRecord({ status: "ok", preset: rec }), rec);
    assert.deepEqual(normalizePresetRecord(rec), rec);
    assert.equal(normalizePresetRecord(null), null);
    assert.equal(normalizePresetRecord({ status: "ok" }), null);
  });
});

// ── Active preset identity (separate from legacy presetId) ────────────────

describe("active preset identity", () => {
  it("round-trips preset + version + revision", () => {
    saveActivePreset({ presetId: "p1", workflowVersionId: "v1", updatedAt: "t1" });
    assert.deepEqual(loadActivePreset(), { presetId: "p1", workflowVersionId: "v1", updatedAt: "t1" });
  });

  it("clears without touching other keys", () => {
    _lsStore.set("comfymodal.studio.playground.drafts.v1", "{}");
    saveActivePreset({ presetId: "p1", workflowVersionId: "v1", updatedAt: "t1" });
    clearActivePreset();
    assert.equal(loadActivePreset(), null);
    assert.equal(_lsStore.get("comfymodal.studio.playground.drafts.v1"), "{}");
  });

  it("rejects empty preset ids", () => {
    saveActivePreset({ presetId: "", workflowVersionId: "v1", updatedAt: "t1" });
    assert.equal(loadActivePreset(), null);
  });
});

describe("revision-keyed working drafts", () => {
  const draft = { core: { positive_prompt: "hi" } };

  it("restores only the matching revision", () => {
    assert.equal(savePresetWorkingDraft("v1", "p1", "t1", draft), true);
    assert.deepEqual(loadPresetWorkingDraft("v1", "p1", "t1"), draft);
    assert.equal(loadPresetWorkingDraft("v1", "p1", "t2"), null);
    assert.equal(loadPresetWorkingDraft("v1", "p2", "t1"), null);
    assert.equal(loadPresetWorkingDraft("v2", "p1", "t1"), null);
  });

  it("returns a detached copy", () => {
    savePresetWorkingDraft("v1", "p1", "t1", draft);
    const loaded = loadPresetWorkingDraft("v1", "p1", "t1");
    loaded.core.positive_prompt = "mutated";
    assert.equal(loadPresetWorkingDraft("v1", "p1", "t1").core.positive_prompt, "hi");
  });

  it("explicit Load replaces the scope draft", () => {
    savePresetWorkingDraft("v1", "p1", "t1", draft);
    savePresetWorkingDraft("v1", "p1", "t2", { core: {} });
    assert.equal(loadPresetWorkingDraft("v1", "p1", "t1"), null);
    assert.deepEqual(loadPresetWorkingDraft("v1", "p1", "t2"), { core: {} });
  });

  it("refuses image-bearing drafts (fail closed, stores nothing)", () => {
    assert.equal(savePresetWorkingDraft("v1", "p1", "t1", { core: { a: "data:image/png;base64,x" } }), false);
    assert.equal(savePresetWorkingDraft("v1", "p1", "t1", { mask: "m.png" }), false);
    assert.equal(loadPresetWorkingDraft("v1", "p1", "t1"), null);
  });

  it("clears per scope", () => {
    savePresetWorkingDraft("v1", "p1", "t1", draft);
    clearPresetWorkingDraft("v1", "p1");
    assert.equal(loadPresetWorkingDraft("v1", "p1", "t1"), null);
  });
});

// ── Exact-version overrides + effective output options ────────────────────

describe("preset core overrides", () => {
  function storeWithSchema() {
    const store = createWorkflowRunStore();
    store.setWorkflowId("w1");
    store.setVersionId("v1");
    store.setRunContext({
      workflow: {},
      version: { workflow_version_id: "v1", state: { runnable: true } },
      mapping: {},
      control_schema: {
        prompt: { node_id: "1", input_name: "text", control_kind: "text" },
        negative_prompt: { node_id: "1", input_name: "neg", control_kind: "text" },
        steps: { node_id: "2", input_name: "steps", control_kind: "number" },
        source_image: { node_id: "3", input_name: "image", control_kind: "image" },
      },
    });
    return store;
  }

  it("applies schema-known roles on exact version match", () => {
    const store = storeWithSchema();
    const res = applyPresetCoreOverrides(
      store,
      { core: { positive_prompt: "a lighthouse", negative_prompt: "blur", controls: { steps: 28 } } },
      { expectedVersionId: "v1" }
    );
    assert.equal(res.ok, true);
    assert.equal(store.controlValues.prompt, "a lighthouse");
    assert.equal(store.controlValues.negative_prompt, "blur");
    assert.equal(store.controlValues.steps, 28);
  });

  it("refuses cross-version apply without touching the store", () => {
    const store = storeWithSchema();
    store.controlValues = { steps: 20 };
    const res = applyPresetCoreOverrides(store, { core: { controls: { steps: 28 } } }, { expectedVersionId: "v2" });
    assert.equal(res.ok, false);
    assert.deepEqual(store.controlValues, { steps: 20 });
  });

  it("never sets image-control roles from a preset", () => {
    const store = storeWithSchema();
    applyPresetCoreOverrides(
      store,
      { core: { controls: { source_image: "evil.png", steps: 28 } } },
      { expectedVersionId: "v1" }
    );
    assert.ok(!("source_image" in store.controlValues));
    assert.equal(store.controlValues.steps, 28);
  });

  it("clears the prompt on empty presets (replace, never inherit)", () => {
    const store = storeWithSchema();
    store.controlValues = { prompt: "stale prompt", steps: 20 };
    const res = applyPresetCoreOverrides(
      store,
      { core: { positive_prompt: "", negative_prompt: "", controls: {} } },
      { expectedVersionId: "v1" }
    );
    assert.equal(res.ok, true);
    assert.equal(store.controlValues.prompt, "");
  });

  it("clears stale prompts even when the schema lost the role (stale mapping)", () => {
    const store = createWorkflowRunStore();
    store.setWorkflowId("w1");
    store.setVersionId("v1");
    store.setRunContext({
      workflow: {},
      version: { workflow_version_id: "v1", state: { runnable: true } },
      mapping: {},
      // Stale-mapping shape: the prompt node is not in the graph, so the
      // schema carries no prompt role — only scalar roles like seed.
      control_schema: {
        seed: { node_id: "2", input_name: "seed", control_kind: "number" },
      },
    });
    store.controlValues = { prompt: "stale prompt", seed: 12345 };
    const res = applyPresetCoreOverrides(
      store,
      { core: { positive_prompt: "", controls: {} } },
      { expectedVersionId: "v1" }
    );
    assert.equal(res.ok, true);
    assert.equal(store.controlValues.prompt, "");
    assert.equal(store.controlValues.seed, 12345);
  });

  it("writes a non-empty prompt mapping-independently, but never invents empty keys", () => {
    const store = createWorkflowRunStore();
    store.setWorkflowId("w1");
    store.setVersionId("v1");
    store.setRunContext({
      workflow: {},
      version: { workflow_version_id: "v1", state: { runnable: true } },
      mapping: {},
      control_schema: {
        seed: { node_id: "2", input_name: "seed", control_kind: "number" },
      },
    });
    store.controlValues = { seed: 1 };
    applyPresetCoreOverrides(store, { core: { positive_prompt: "visible prompt", controls: {} } }, {});
    assert.equal(store.controlValues.prompt, "visible prompt");
    // Empty on a prompt-less version invents nothing (no new unknown-role
    // validation error downstream).
    const bare = createWorkflowRunStore();
    bare.setWorkflowId("w1");
    bare.setVersionId("v1");
    bare.setRunContext({
      workflow: {},
      version: { workflow_version_id: "v1", state: { runnable: true } },
      mapping: {},
      control_schema: {
        seed: { node_id: "2", input_name: "seed", control_kind: "number" },
      },
    });
    bare.controlValues = { seed: 1 };
    applyPresetCoreOverrides(bare, { core: { positive_prompt: "", controls: {} } }, {});
    assert.ok(!("prompt" in bare.controlValues));
    assert.ok(!("positive_prompt" in bare.controlValues));
  });

  it("drops schema-unknown roles", () => {
    const store = storeWithSchema();
    applyPresetCoreOverrides(store, { core: { controls: { nope: 1, steps: 5 } } }, {});
    assert.ok(!("nope" in store.controlValues));
  });
});

describe("effective output options", () => {
  it("overlays flat preset output onto globals without mutating inputs", () => {
    const base = { output_format: "original", quality: 75, preview_quality: 70 };
    const out = resolveEffectiveOutputOptions(base, {
      output_format: "png",
      quality: 90,
      auto_save_local: true,
      save_folder: "output/modal",
      preview_default: "on",
      preview_quality: 80,
    });
    assert.equal(out.output_format, "png");
    assert.equal(out.quality, 90);
    assert.equal(out.auto_save_local, true);
    assert.equal(out.save_folder, "output/modal");
    assert.equal(out.preview_default, "on");
    assert.equal(out.data_saver_default, "on");
    assert.equal(out.preview_quality, 80);
    assert.equal(base.output_format, "original");
  });

  it("passes globals through untouched without a preset section", () => {
    const base = { output_format: "png", quality: 90 };
    assert.deepEqual(resolveEffectiveOutputOptions(base, null), base);
    assert.notEqual(resolveEffectiveOutputOptions(base, null), base);
  });
});

// ── Owner hooks ───────────────────────────────────────────────────────────

describe("layout preset hooks", () => {
  function fakeEditor() {
    let draft = {
      boxes: [],
      high_level_description: "",
      background: "",
      style_mode: "none",
      color_palette: [],
      width: 1024,
      height: 1024,
    };
    return {
      getDraft: () => JSON.parse(JSON.stringify(draft)),
      setDraft: (next) => { draft = Object.assign({}, draft, next); },
    };
  }

  it("snapshots the detached native draft", () => {
    const editor = fakeEditor();
    const snap = snapshotLayoutForPreset(editor);
    assert.deepEqual(snap.boxes, []);
    snap.boxes.push({ id: "x" });
    assert.deepEqual(editor.getDraft().boxes, []);
  });

  it("applies a flat contract section through setDraft and resets to neutral", () => {
    const editor = fakeEditor();
    assert.equal(
      applyLayoutFromPreset(editor, {
        high_level_description: "hero",
        background: "coast",
        style_mode: "photo",
        color_palette: "#112233,#445566",
        width: 512,
        height: 512,
        bgBrightness: 25,
        boxes: [{ id: "b1", type: "text", color_palette: "#ff0000" }],
      }),
      true
    );
    const draft = editor.getDraft();
    assert.equal(draft.high_level_description, "hero");
    assert.equal(draft.boxes.length, 1);
    assert.deepEqual(draft.color_palette, ["#112233", "#445566"]);
    assert.deepEqual(draft.boxes[0].color_palette, ["#ff0000"]);
    assert.equal(resetLayoutForPreset(editor), true);
    const neutral = editor.getDraft();
    assert.deepEqual(neutral.boxes, []);
    assert.equal(neutral.high_level_description, "");
  });

  it("returns false without a live editor", () => {
    assert.equal(applyLayoutFromPreset(null, {}), false);
    assert.equal(resetLayoutForPreset(null), false);
    assert.equal(snapshotLayoutForPreset(null), null);
  });
});

describe("guidance preset hooks", () => {
  it("snapshots confirmed-mapping config without any guide image", () => {
    const snap = snapshotGuidanceForPreset({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA64.toUpperCase() },
      mapping: {
        record: {
          model_sha256: SHA64,
          mode: "canny",
          mechanism: "CONTROLNET_CONDITIONING",
          revision: "r3",
          controller: { checkpoint: "ctrl.safetensors", folder: "controlnet", checkpoint_sha256: "" },
          nodes: { loader: "L", apply: "A", preprocessor: "P" },
          conditioning: { strength: 0.7, start: 0, end: 0.8 },
        },
      },
      conditioning: {},
    });
    assert.equal(snap.engaged, true);
    assert.equal(snap.model_sha256, SHA64);
    assert.equal(snap.mapping_revision, "r3");
    assert.deepEqual(snap.controller, {
      checkpoint: "ctrl.safetensors",
      folder: "controlnet",
      checkpoint_sha256: "",
    });
    assert.ok(!("guideImage" in snap));
    assert.ok(!("guide_image" in snap));
  });

  it("drops malformed digests and stringifies revisions", () => {
    const snap = snapshotGuidanceForPreset({
      engaged: true,
      identity: { status: "resolved", sha: "SHORT" },
      mapping: { record: { revision: 7 } },
      conditioning: {},
    });
    assert.equal(snap.model_sha256, "");
    assert.equal(snap.mapping_revision, "7");
  });

  it("applies engagement into a fresh input without writing mappings", () => {
    const next = applyGuidanceFromPreset(
      { engaged: false },
      { engaged: true, mode: "depth", model_sha256: SHA64, mapping_revision: "r2", conditioning: { strength: 0.5, start: 0, end: 1 } }
    );
    assert.equal(next.engaged, true);
    assert.equal(next.mode, "depth");
    assert.equal(next.presetModelSha256, SHA64);
    assert.equal(next.presetMappingRevision, "r2");
    const off = applyGuidanceFromPreset(next, null);
    assert.equal(off.engaged, false);
    const reset = resetGuidanceForPreset(next);
    assert.equal(reset.engaged, false);
    assert.ok(!("presetModelSha256" in reset));
  });

  it("never references mapping-save/confirm APIs (static gate)", () => {
    const src = readFileSync(join(WEB_DIR, "studio-guidance.js"), "utf8");
    assert.ok(!src.includes("saveGuidanceMapping"));
    assert.ok(!src.includes("confirmMapping"));
    assert.ok(!/^\s*import\s/m.test(src), "guidance module must stay import-free");
  });
});

describe("sketch preset hooks", () => {
  it("snapshots settings without pixels and round-trips apply/reset", () => {
    const session = openSketch({ mode: "generate", width: 512, height: 512 });
    session.setToolSettings({ tool: "pencil", brushSize: 4, color: "#ff0000" });
    const snap = snapshotSketchSettingsForPreset(session);
    assert.equal(snap.tool, "pencil");
    assert.equal(snap.brushSize, 4);
    assert.equal(snap.width, 512);
    assert.ok(!("baseImageUrl" in snap));
    assert.equal(applySketchSettingsFromPreset(session, { tool: "brush", brushSize: 9 }), true);
    assert.equal(session.getToolSettings().brushSize, 9);
    assert.equal(resetSketchForPreset(session), true);
    assert.equal(session.getToolSettings().tool, "brush");
    clearSketchBaseForPreset(session);
    assert.equal(applySketchSettingsFromPreset(null, {}), false);
    session.destroy();
  });

  it("prefers live engine state over stale session settings (settings only, no pixels)", () => {
    // The tool panels drive the engine directly (setSize/setColor/...), so a
    // slider drag to 24 + a red swatch click land in engine.getState() while
    // session settings stay stale — capture must read the engine source.
    const session = openSketch({ mode: "generate", width: 512, height: 512 });
    session.setToolSettings({ tool: "brush", brushSize: 8, color: "" });
    const engineState = {
      tool: "brush",
      brushSize: 24,
      opacity: 1,
      hardness: 0.8,
      color: "#ff0000",
      bgColor: "#ffffff",
      zoom: 1,
      layerCount: 1,
    };
    const snap = snapshotSketchSettingsForPreset(session, engineState);
    assert.equal(snap.tool, "brush");
    assert.equal(snap.brushSize, 24);
    assert.equal(snap.color, "#ff0000");
    assert.equal(snap.bgColor, "#ffffff");
    assert.equal(snap.width, 512);
    assert.equal(snap.height, 512);
    const serialized = JSON.stringify(snap);
    assert.ok(!serialized.includes("baseImage"));
    assert.ok(!serialized.includes("pixel"));
    assert.ok(!serialized.includes("layer"));
    // Session-only path still stands alone (preset apply feeds the session).
    const alone = snapshotSketchSettingsForPreset(session, null);
    assert.equal(alone.brushSize, 8);
    session.destroy();
  });
});

describe("postprocess preset hooks", () => {
  it("projects the frozen recipe scalars only", () => {
    const snap = snapshotPostRecipeForPreset(
      Object.assign(defaultRecipe(), {
        format: "png",
        quality: 95,
        embedMetadata: true,
        exposure: 5,
        curves: { master: [[0, 0]] },
        spots: [{ x: 0.1, y: 0.1, r: 5 }],
        lutId: "filmic",
      })
    );
    assert.equal(snap.format, "png");
    assert.equal(snap.quality, 95);
    assert.equal(snap.embedMetadata, true);
    assert.ok(!("exposure" in snap));
    assert.ok(!("curves" in snap));
    assert.ok(!("spots" in snap));
    assert.ok(!("lutId" in snap));
  });

  it("merges patches over defaults and seeds neutral on null", () => {
    const merged = mergePostRecipeForPreset(defaultRecipe(), { recipe: { format: "jpeg" } });
    assert.equal(merged.format, "jpeg");
    const neutral = neutralPostRecipeForPreset();
    assert.deepEqual(neutral, snapshotPostRecipeForPreset(defaultRecipe()));
    const seeded = applyPostRecipeForPreset({ recipe: { quality: 80 } });
    assert.equal(seeded.quality, 80);
    const reset = applyPostRecipeForPreset(null);
    assert.deepEqual(reset, snapshotPostRecipeForPreset(defaultRecipe()));
    clearPostPresetPending();
  });
});

describe("output preset override builder", () => {
  it("builds a bounded flat override and null when absent", () => {
    assert.equal(buildPresetOutputOverride(null), null);
    assert.equal(buildPresetOutputOverride({}), null);
    const over = buildPresetOutputOverride({
      output_format: "bogus",
      quality: 90,
      auto_save_local: true,
      save_folder: "output/modal",
      preview_default: "on",
      preview_quality: 80,
      data_saver_default: "on",
    });
    assert.ok(!("output_format" in over), "unknown formats are dropped");
    assert.ok(!("data_saver_default" in over), "non-contract aliases are dropped");
    assert.equal(over.quality, 90);
    assert.equal(over.save_folder, "output/modal");
    assert.equal(over.preview_default, "on");
  });

  it("drops image-like folders", () => {
    const over = buildPresetOutputOverride({ save_folder: "https://x/y" });
    assert.equal(over, null);
  });
});
