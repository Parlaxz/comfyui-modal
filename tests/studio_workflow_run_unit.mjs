// Modal Studio — Workflow Run Frontend Logic Unit Tests
//
// Executable behavioral tests that import and run the actual module
// (web/studio-workflow-run.js) with a hand-written rich fake run-context
// bundle (txt2img-like). No browser, no DOM, plain Node.
//
// localStorage access is guarded inside the module, so the shim below is
// defined before any persistence function is called (the module reads
// localStorage lazily inside functions — defining globalThis.localStorage
// mid-script is sufficient).
//
// Run: node tests/studio_workflow_run_unit.mjs

import assert from "node:assert/strict";
import {
  createWorkflowRunStore,
  defaultValuesFromContext,
  validateMappedValues,
  mergePresetAndOverrides,
  resolveRunnable,
  buildRunPayload,
  modelCompatibility,
  saveWorkflowSelection,
  loadWorkflowSelection,
  clearWorkflowSelection,
  saveWorkflowHandoff,
  takeWorkflowHandoff,
  resolveHandoffSelection,
  getControlSchema,
} from "../web/studio-workflow-run.js";

// ── localStorage shim (guarded reads inside the module) ──────────────────

{
  const backing = new Map();
  globalThis.localStorage = {
    getItem: (k) => (backing.has(k) ? backing.get(k) : null),
    setItem: (k, v) => { backing.set(String(k), String(v)); },
    removeItem: (k) => { backing.delete(String(k)); },
    clear: () => { backing.clear(); },
    key: (i) => [...backing.keys()][i] ?? null,
    get length() { return backing.size; },
  };
}

// ── Helpers ──────────────────────────────────────────────────────────────

/** Report a section as passing. */
function section(name) {
  console.log("PASS: " + name);
}

/** Fixed fake model library records (installed/missing) used everywhere. */
function fakeModelLibrary() {
  return [
    { filename: "sd15_v2.safetensors", folder: "checkpoints", installed: true, state: "installed" },
    { filename: "krea_model.safetensors", folder: "checkpoints", installed: false, state: "missing" },
  ];
}

/**
 * Build the rich fake run-context bundle. The graph matches the control
 * schema exactly (txt2img-like: two CLIPTextEncode, KSampler,
 * CheckpointLoaderSimple, EmptyLatentImage, bool node, SaveImage).
 */
function makeRunContext(overrides = {}) {
  const executablePrompt = {
    "3": {
      class_type: "KSampler",
      inputs: {
        model: ["9", 0], seed: 0, steps: 20, cfg: 7.0,
        sampler_name: "euler", scheduler: "normal",
        positive: ["6", 0], negative: ["7", 0], latent_image: ["5", 0],
        denoise: 1.0,
      },
    },
    "6": { class_type: "CLIPTextEncode", inputs: { text: "hello world", clip: ["9", 1] } },
    "7": { class_type: "CLIPTextEncode", inputs: { text: "negative", clip: ["9", 1] } },
    "5": { class_type: "EmptyLatentImage", inputs: { width: 512, height: 512, batch_size: 1 } },
    "9": { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: "sd15_v2.safetensors" } },
    "8": { class_type: "SomeBooleanNode", inputs: { boolean: false } },
    "4": { class_type: "SaveImage", inputs: { images: ["3", 0] } },
  };

  const entries = [
    { semantic_role: "prompt", node_id: "6", input_name: "text", kind: "node_input", control_kind: "multiline", data_type: "STRING", multiline: true, required: true },
    { semantic_role: "negative_prompt", node_id: "7", input_name: "text", kind: "node_input", control_kind: "multiline", data_type: "STRING", multiline: true, required: false },
    { semantic_role: "seed", node_id: "3", input_name: "seed", kind: "node_input", control_kind: "integer", data_type: "INT", minimum: -1, maximum: 281474976710655, step: 1, required: true },
    { semantic_role: "steps", node_id: "3", input_name: "steps", kind: "node_input", control_kind: "integer", data_type: "INT", minimum: 1, maximum: 100, step: 1, required: true },
    { semantic_role: "cfg", node_id: "3", input_name: "cfg", kind: "node_input", control_kind: "number", data_type: "FLOAT", minimum: 0, maximum: 30, step: 0.5, required: false },
    { semantic_role: "sampler", node_id: "3", input_name: "sampler_name", kind: "node_input", control_kind: "enum", data_type: "ENUM", enum_options: ["euler", "dpmpp_2m", "uni_pc"], required: true },
    { semantic_role: "scheduler", node_id: "3", input_name: "scheduler", kind: "node_input", control_kind: "enum", data_type: "ENUM", enum_options: ["normal", "karras", "sgm_uniform"], required: true },
    { semantic_role: "denoise", node_id: "3", input_name: "denoise", kind: "node_input", control_kind: "number", data_type: "FLOAT", minimum: 0, maximum: 1, step: 0.01, required: false },
    { semantic_role: "model", node_id: "9", input_name: "ckpt_name", kind: "node_input", control_kind: "file", data_type: "CHECKPOINT", enum_options: ["sd15_v2.safetensors", "krea_model.safetensors"], required: true },
    { semantic_role: "width", node_id: "5", input_name: "width", kind: "node_input", control_kind: "integer", data_type: "INT", minimum: 64, maximum: 2048, step: 8, required: true },
    { semantic_role: "height", node_id: "5", input_name: "height", kind: "node_input", control_kind: "integer", data_type: "INT", minimum: 64, maximum: 2048, step: 8, required: true },
    { semantic_role: "bool_toggle", node_id: "8", input_name: "boolean", kind: "node_input", control_kind: "boolean", data_type: "BOOLEAN", required: false },
  ];

  const controlSchema = {};
  for (const e of entries) controlSchema[e.semantic_role] = e;

  const version = {
    workflow_version_id: "wv1_latest",
    version_number: 2,
    executable_prompt: executablePrompt,
    graph_hash: "ab" + "0".repeat(62),
    state: { status: "ready", reasons: [], runnable: true },
    mapping_id: "wm_latest",
    mapping: { mapping_id: "wm_latest", workflow_version_id: "wv1_latest", output_node_id: "4", entries },
    preset_count: 2,
    compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
  };

  const workflow = {
    workflow_id: "wf_text2img",
    name: "Text2Img Workflow",
    description: "txt2img fixture",
    folder: "",
    tags: [],
    favorite: false,
    latest_version_id: "wv1_latest",
    latest_version_number: 2,
    latest_version_state: { status: "ready", reasons: [], runnable: true },
    default_preset_id: "wpres_a",
    compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
    updated_at: "2026-01-01T00:00:00.000Z",
  };

  const defaultPreset = {
    preset_id: "wpres_a",
    workflow_version_id: "wv1_latest",
    workflow_id: "wf_text2img",
    name: "Preset A",
    values: { prompt: "preset A prompt", seed: 111, steps: 25 },
    model_choices: { model: "sd15_v2.safetensors" },
    state: { status: "ready", reasons: [], runnable: true },
    is_default: true,
  };

  const base = {
    status: "ok",
    workflow,
    version,
    mapping: { mapping_id: "wm_latest", workflow_version_id: "wv1_latest", output_node_id: "4", entries },
    default_preset: defaultPreset,
    state: { status: "ready", reasons: [], runnable: true },
    control_schema: controlSchema,
  };

  return Object.assign(base, overrides);
}

/** Store configured like the Playground after a full workflow selection. */
function makeSelectedStore(ctx = makeRunContext()) {
  const store = createWorkflowRunStore();
  store.setWorkflowId(ctx.workflow.workflow_id);
  store.setWorkflowName(ctx.workflow.name);
  store.setVersionId(ctx.version.workflow_version_id);
  store.setPresetId(ctx.default_preset.preset_id);
  store.setPresetName(ctx.default_preset.name);
  store.setLibrary([ctx.workflow]);
  store.setVersions([ctx.version]);
  store.setPresets([ctx.default_preset]);
  store.setRunContext(ctx);
  store.setStatus("ready");
  store.controlValues = defaultValuesFromContext(store, ctx.default_preset);
  return store;
}

// ── 1. defaultValuesFromContext ──────────────────────────────────────────

{
  const ctx = makeRunContext();
  const store = makeSelectedStore(ctx);
  const defaults = store.controlValues;

  // Preset values win over graph defaults.
  assert.equal(defaults.prompt, "preset A prompt", "preset prompt wins over graph text");
  assert.equal(defaults.seed, 111, "preset seed wins over graph seed 0");
  assert.equal(defaults.steps, 25, "preset steps win over graph steps 20");

  // Graph defaults read verbatim from executable_prompt when not in preset.
  assert.equal(defaults.cfg, 7.0, "cfg read verbatim from graph (float)");
  assert.equal(defaults.sampler, "euler", "sampler read verbatim from graph");
  assert.equal(defaults.scheduler, "normal", "scheduler read verbatim from graph");
  assert.equal(defaults.denoise, 1.0, "denoise read verbatim from graph");
  assert.equal(defaults.width, 512, "width read verbatim from graph");
  assert.equal(defaults.height, 512, "height read verbatim from graph");
  assert.equal(defaults.negative_prompt, "negative", "negative_prompt read verbatim from graph");
  assert.equal(defaults.model, "sd15_v2.safetensors", "model_choice wins for the model role");

  // 0 preserved: graph seed 0 is kept when no preset value (0 not dropped).
  const noSeedPreset = {
    preset_id: "wpres_b", workflow_version_id: "wv1_latest", name: "Preset B",
    values: { prompt: "preset B prompt", steps: 30 },
    model_choices: { model: "sd15_v2.safetensors" },
  };
  const ctxB = makeRunContext({ default_preset: noSeedPreset });
  const storeB = createWorkflowRunStore();
  storeB.setRunContext(ctxB);
  const defaultsB = defaultValuesFromContext(storeB, noSeedPreset);
  assert.equal(defaultsB.seed, 0, "graph seed 0 is preserved as 0, not undefined");
  assert.equal(defaultsB.steps, 30, "preset steps still applied");

  // false preserved for boolean (graph value false).
  assert.equal(defaults.bool_toggle, false, "boolean graph value false preserved");

  // "" preserved for string (graph prompt "").
  const emptyPromptCtx = makeRunContext();
  emptyPromptCtx.version.executable_prompt["6"].inputs.text = "";
  const storeEmpty = createWorkflowRunStore();
  storeEmpty.setRunContext(emptyPromptCtx);
  const defaultsEmpty = defaultValuesFromContext(storeEmpty, null);
  assert.equal(defaultsEmpty.prompt, "", "empty string prompt preserved verbatim");

  // enum → enum_options[0] when neither preset nor graph defines a value.
  const noSamplerCtx = makeRunContext();
  noSamplerCtx.default_preset = null;
  delete noSamplerCtx.version.executable_prompt["3"].inputs.sampler_name;
  const storeNS = createWorkflowRunStore();
  storeNS.setRunContext(noSamplerCtx);
  const defaultsNS = defaultValuesFromContext(storeNS, null);
  assert.equal(defaultsNS.sampler, "euler", "required enum falls back to enum_options[0]");
  assert.equal(defaultsNS.cfg, 7.0, "non-enum role still reads the graph");
  section("1. defaultValuesFromContext");
}

// ── 2. validateMappedValues ──────────────────────────────────────────────

{
  const schema = getControlSchema(makeSelectedStore());

  // Unknown role rejected.
  const unknown = validateMappedValues({ not_a_control: 1 }, schema);
  assert.ok(unknown.errors.some((e) => e.field === "not_a_control" && /unknown control/.test(e.message)),
    "unknown role produces an unknown-control error");
  assert.equal(Object.prototype.hasOwnProperty.call(unknown.values, "not_a_control"), false,
    "unknown role never lands in cleaned values");

  // Enum exact: trailing space rejected, exact accepted.
  const badSampler = validateMappedValues({ sampler: "euler " }, schema);
  assert.ok(badSampler.errors.some((e) => e.field === "sampler" && /must be one of/.test(e.message)),
    "sampler 'euler ' rejected (enum exact)");
  const goodSampler = validateMappedValues({ sampler: "euler" }, schema);
  assert.equal(goodSampler.errors.some((e) => e.field === "sampler"), false,
    "sampler 'euler' accepted (no sampler error)");

  // 0 within min/max accepted (seed min is -1, so 0 is legal).
  const zero = validateMappedValues({ seed: 0 }, schema);
  assert.equal(zero.errors.some((e) => e.field === "seed"), false,
    "seed 0 accepted (0 is within min/max)");

  // 0.0 accepted for float.
  const zeroFloat = validateMappedValues({ cfg: 0.0 }, schema);
  assert.equal(zeroFloat.errors.some((e) => e.field === "cfg"), false, "cfg 0.0 accepted");

  // false accepted for bool.
  const boolFalse = validateMappedValues({ bool_toggle: false }, schema);
  assert.equal(boolFalse.errors.some((e) => e.field === "bool_toggle"), false, "bool_toggle false accepted");

  // "" rejected for required string role only when required.
  const emptyRequired = validateMappedValues({ prompt: "" }, schema);
  assert.ok(emptyRequired.errors.some((e) => e.field === "prompt" && e.message === "required"),
    "required prompt '' rejected");
  const emptyOptional = validateMappedValues({ negative_prompt: "" }, schema);
  assert.equal(emptyOptional.errors.some((e) => e.field === "negative_prompt"), false,
    "optional negative_prompt '' accepted");

  // Missing required role → completeness error.
  const missing = validateMappedValues({}, schema);
  assert.ok(missing.errors.some((e) => /missing required control 'steps'/.test(e.message)),
    "missing required role yields a completeness error");

  // Min/max violations rejected.
  const minViolation = validateMappedValues({ steps: 0, seed: 0 }, { steps: schema.steps, seed: schema.seed });
  assert.ok(minViolation.errors.some((e) => e.field === "steps" && /must be >= 1/.test(e.message)),
    "steps 0 below min 1 rejected");
  const maxViolation = validateMappedValues({ steps: 101 }, { steps: schema.steps });
  assert.ok(maxViolation.errors.some((e) => e.field === "steps" && /must be <= 100/.test(e.message)),
    "steps 101 above max 100 rejected");

  // Step not enforced (only min/max).
  const offStep = validateMappedValues({ width: 100 }, { width: schema.width });
  assert.equal(offStep.errors.length, 0, "width 100 not rejected despite step 8 (step is not enforced)");
  section("2. validateMappedValues");
}

// ── 3. mergePresetAndOverrides ───────────────────────────────────────────

{
  const schema = getControlSchema(makeSelectedStore());
  const preset = {
    preset_id: "wpres_a", workflow_version_id: "wv1_latest", name: "Preset A",
    values: { prompt: "from preset", seed: 111, steps: 25 },
    model_choices: { model: "krea_model.safetensors" },
  };

  // Preset values applied.
  const merged = mergePresetAndOverrides(preset, {}, schema);
  assert.equal(merged.values.prompt, "from preset");
  assert.equal(merged.values.seed, 111);
  assert.equal(merged.values.steps, 25);

  // model_choices applied for the model role (overrides plain values).
  assert.equal(merged.values.model, "krea_model.safetensors", "model_choice wins over values");

  // Override wins over preset.
  const overridden = mergePresetAndOverrides(preset, { seed: 999, steps: 40 }, schema);
  assert.equal(overridden.values.seed, 999, "override seed wins");
  assert.equal(overridden.values.steps, 40, "override steps wins");
  assert.equal(overridden.values.prompt, "from preset", "unoverridden preset value kept");

  // Errors surfaced.
  const bad = mergePresetAndOverrides(preset, { steps: 0 }, schema);
  assert.ok(bad.errors.some((e) => e.field === "steps" && /must be >= 1/.test(e.message)),
    "invalid override error surfaced");

  // Verbatim falsy preservation through merge.
  const falsy = mergePresetAndOverrides({ values: { seed: 0, cfg: 0.0, bool_toggle: false } }, {}, schema);
  assert.equal(falsy.values.seed, 0);
  assert.equal(falsy.values.cfg, 0.0);
  assert.equal(falsy.values.bool_toggle, false);
  assert.equal(falsy.errors.some((e) => ["seed", "cfg", "bool_toggle"].includes(e.field)), false,
    "falsy preset values are valid (only completeness errors remain)");
  section("3. mergePresetAndOverrides");
}

// ── 4. resolveRunnable ───────────────────────────────────────────────────

{
  // false when runContext null.
  const empty = createWorkflowRunStore();
  const r1 = resolveRunnable(empty);
  assert.equal(r1.runnable, false);
  assert.ok(r1.reasons.includes("no run context"));

  // false when version.state.runnable false (reasons passed verbatim).
  const unrunnableCtx = makeRunContext();
  unrunnableCtx.version.state = {
    status: "incomplete",
    reasons: ["missing custom node 'X'"],
    runnable: false,
  };
  const storeBad = createWorkflowRunStore();
  storeBad.setRunContext(unrunnableCtx);
  storeBad.setWorkflowId("wf_text2img");
  storeBad.setVersionId("wv1_latest");
  storeBad.setPresetId("wpres_a");
  storeBad.setStatus("ready");
  const r2 = resolveRunnable(storeBad);
  assert.equal(r2.runnable, false);
  assert.ok(r2.reasons.includes("missing custom node 'X'"), "backend reason passed through verbatim");

  // false when no preset selected.
  const noPreset = makeSelectedStore();
  noPreset.setPresetId("");
  const r3 = resolveRunnable(noPreset);
  assert.equal(r3.runnable, false);
  assert.ok(r3.reasons.includes("no preset selected for version"));

  // false when control validation errors.
  const badControl = makeSelectedStore();
  badControl.setControlValue("steps", 0);
  const r4 = resolveRunnable(badControl);
  assert.equal(r4.runnable, false);
  assert.ok(r4.reasons.some((reason) => /must be >= 1/.test(reason)), "validation error gates the run");

  // true when all good.
  const good = makeSelectedStore();
  const r5 = resolveRunnable(good);
  assert.equal(r5.runnable, true);
  assert.deepEqual(r5.reasons, []);
  section("4. resolveRunnable");
}

// ── 5. buildRunPayload ───────────────────────────────────────────────────

{
  const ctx = makeRunContext();
  const store = makeSelectedStore(ctx);
  store.setControlValue("seed", 7);

  const payload = buildRunPayload("/comfymodal", store, { execution_mode: "v2" }, { t0_perf_ms: 1 });

  // Exact top-level keys.
  assert.deepEqual(
    Object.keys(payload).sort(),
    ["controls", "featureId", "metadata", "modal_options", "preset_id", "trace", "workflow_id", "workflow_version_id"],
    "payload carries exactly the 8 contract keys"
  );
  assert.equal(payload.workflow_id, "wf_text2img");
  assert.equal(payload.workflow_version_id, "wv1_latest");
  assert.equal(payload.preset_id, "wpres_a");
  assert.equal(payload.featureId, "txt2img");
  assert.deepEqual(payload.modal_options, { execution_mode: "v2" });
  assert.deepEqual(payload.trace, { t0_perf_ms: 1 });

  // Controls contain ONLY schema roles.
  const schema = getControlSchema(store);
  for (const role of Object.keys(payload.controls)) {
    assert.ok(schema[role], `control ${role} is a schema role`);
  }
  assert.ok(payload.controls.seed, "controls carries seed");
  assert.ok(payload.controls.prompt, "controls carries prompt");
  assert.equal(payload.controls.seed, 7, "override value lands in controls");

  // Metadata carries source + all 5 identity keys.
  assert.equal(payload.metadata.source, "studio_playground");
  assert.equal(payload.metadata.workflow_id, "wf_text2img");
  assert.equal(payload.metadata.workflow_version_id, "wv1_latest");
  assert.equal(payload.metadata.preset_id, "wpres_a");
  assert.equal(payload.metadata.workflow_name, "Text2Img Workflow");
  assert.equal(payload.metadata.preset_name, "Preset A");
  assert.equal(payload.metadata.workflow_hash, ctx.version.graph_hash, "workflow_hash = graph_hash");
  section("5. buildRunPayload");
}

// ── 6. modelCompatibility ────────────────────────────────────────────────

{
  const store = makeSelectedStore();
  const compat = modelCompatibility(store, fakeModelLibrary());

  // compatible + installed.
  const installed = compat.byFilename["sd15_v2.safetensors"];
  assert.deepEqual(installed, { compatible: true, installed: true });

  // compatible + missing.
  const missing = compat.byFilename["krea_model.safetensors"];
  assert.deepEqual(missing, { compatible: true, installed: false });

  // filename not in compatible_models → known-incompatible (via the model
  // role enum options which are checked against compatible_models).
  assert.equal(compat.byFilename["evil_model.safetensors"], undefined,
    "evil_model is not in compatible_models so it stays absent");
  // The model-role enum option check only flags options PRESENT in the enum.
  const compatWithEvil = modelCompatibility(store, fakeModelLibrary());
  const evilCtx = makeRunContext();
  const modelEntry = evilCtx.control_schema.model;
  modelEntry.enum_options = ["sd15_v2.safetensors", "krea_model.safetensors", "evil_model.safetensors"];
  evilCtx.mapping.entries = evilCtx.mapping.entries.map((e) =>
    e.semantic_role === "model" ? { ...e, enum_options: modelEntry.enum_options } : e
  );
  const storeEvil = createWorkflowRunStore();
  storeEvil.setRunContext(evilCtx);
  const compatEvil = modelCompatibility(storeEvil, fakeModelLibrary());
  assert.deepEqual(compatEvil.byFilename["evil_model.safetensors"], { compatible: false },
    "enum option missing from compatible_models is known-incompatible");
  assert.ok(compatEvil.summary.incompatible >= 1);

  // sampler/scheduler enums never flagged incompatible (not model roles).
  assert.equal(compatEvil.byFilename["euler"], undefined, "sampler enum is not a model filename");
  assert.equal(compatEvil.byFilename["uni_pc"], undefined, "scheduler enum is not a model filename");
  assert.equal(compatEvil.summary.incompatible, 1, "only the model-role option is incompatible");

  // Summary math.
  assert.equal(compat.summary.total, 2);
  assert.equal(compat.summary.compatible, 2);
  assert.equal(compat.summary.installed, 1);
  assert.equal(compat.summary.missing, 1);
  section("6. modelCompatibility");
}

// ── 7. persistence + handoff ─────────────────────────────────────────────

{
  localStorage.clear();

  // save/load round trip.
  saveWorkflowSelection({
    workflowId: "wf_text2img",
    workflowVersionId: "wv1_old",
    presetId: "wpres_b",
    workflowName: "Text2Img Workflow",
    presetName: "Preset B",
  });
  const loaded = loadWorkflowSelection();
  assert.deepEqual(loaded, {
    workflowId: "wf_text2img",
    workflowVersionId: "wv1_old",
    presetId: "wpres_b",
    workflowName: "Text2Img Workflow",
    presetName: "Preset B",
  });
  clearWorkflowSelection();
  assert.equal(loadWorkflowSelection(), null, "cleared selection loads as null");

  // One-shot handoff: returns once, second call null.
  saveWorkflowHandoff({ workflowId: "wf_text2img", workflowVersionId: "wv1_old", presetId: "wpres_a" });
  const handoff1 = takeWorkflowHandoff();
  assert.deepEqual(handoff1, {
    workflowId: "wf_text2img",
    workflowVersionId: "wv1_old",
    presetId: "wpres_a",
    workflowName: "",
    presetName: "",
  });
  assert.equal(takeWorkflowHandoff(), null, "handoff consumed exactly once");
  section("7. persistence + handoff");
}

// ── 8. resolveHandoffSelection ───────────────────────────────────────────

{
  localStorage.clear();
  const ctx = makeRunContext();
  const store = createWorkflowRunStore();
  store.setLibrary([ctx.workflow]);
  store.setVersions([ctx.version, {
    workflow_version_id: "wv1_old", version_number: 1, created_at: "2025-01-01T00:00:00.000Z",
  }]);
  store.setPresets([ctx.default_preset, {
    preset_id: "wpres_b", workflow_version_id: "wv1_latest", name: "Preset B",
  }]);

  // Valid handoff → ok and applied.
  saveWorkflowHandoff({ workflowId: "wf_text2img", workflowVersionId: "wv1_old", presetId: "wpres_b" });
  const ok = resolveHandoffSelection(store);
  assert.equal(ok.ok, true);
  assert.equal(store.workflowId, "wf_text2img");
  assert.equal(store.workflowVersionId, "wv1_old");
  assert.equal(store.presetId, "wpres_b");
  assert.ok(store.handoff, "store keeps the consumed handoff for the notice");

  // Missing version → error, no substitution.
  store.setVersionId("wv1_latest");
  store.setPresetId("wpres_a");
  saveWorkflowHandoff({ workflowId: "wf_text2img", workflowVersionId: "wv_ghost", presetId: "wpres_a" });
  const bad = resolveHandoffSelection(store);
  assert.equal(bad.ok, false);
  assert.ok(bad.error, "error message present");
  assert.equal(store.workflowVersionId, "wv1_latest", "no version substitution on failure");
  assert.equal(store.presetId, "wpres_a", "no preset substitution on failure");

  // Missing preset → error.
  saveWorkflowHandoff({ workflowId: "wf_text2img", workflowVersionId: "wv1_old", presetId: "wpres_ghost" });
  const badPreset = resolveHandoffSelection(store);
  assert.equal(badPreset.ok, false);

  // No handoff at all → clean error.
  const none = resolveHandoffSelection(store);
  assert.equal(none.ok, false);
  assert.equal(none.error, "no handoff selection");
  section("8. resolveHandoffSelection");
}

console.log("PASS: studio workflow run unit tests");
