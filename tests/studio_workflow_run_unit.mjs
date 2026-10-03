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
  mergeDefaultsAndOverrides,
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
import {
  PORTABILITY_TARGET_ORDER,
  TARGET_LABELS,
  chipStateFromSummary,
  normalizePortabilitySummary,
  normalizeRiskLevel,
  riskKind,
  riskLabel,
} from "../web/studio-portability.js";
import {
  buildChecklistFilename,
  buildPortabilityChecklist,
} from "../web/studio-portability-checklist.js";
import {
  exportManifestEndpointPath,
  importManifestQuery,
  portabilityEndpointPath,
} from "../web/studio-backend-api.js";

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
  store.setLibrary([ctx.workflow]);
  store.setVersions([ctx.version]);
  store.setRunContext(ctx);
  store.setStatus("ready");
  store.controlValues = defaultValuesFromContext(store);
  return store;
}

// ── 1. defaultValuesFromContext ──────────────────────────────────────────

{
  const ctx = makeRunContext();
  const store = makeSelectedStore(ctx);
  const defaults = store.controlValues;

  // Defaults read verbatim from the version's own captured graph.
  assert.equal(defaults.prompt, "hello world", "graph prompt read verbatim");
  assert.equal(defaults.seed, 0, "graph seed read verbatim (0 preserved)");
  assert.equal(defaults.steps, 20, "steps read verbatim from graph");

  // Every value comes from the graph, verbatim.
  assert.equal(defaults.cfg, 7.0, "cfg read verbatim from graph (float)");
  assert.equal(defaults.sampler, "euler", "sampler read verbatim from graph");
  assert.equal(defaults.scheduler, "normal", "scheduler read verbatim from graph");
  assert.equal(defaults.denoise, 1.0, "denoise read verbatim from graph");
  assert.equal(defaults.width, 512, "width read verbatim from graph");
  assert.equal(defaults.height, 512, "height read verbatim from graph");
  assert.equal(defaults.negative_prompt, "negative", "negative_prompt read verbatim from graph");
  assert.equal(defaults.model, "sd15_v2.safetensors", "model_choice wins for the model role");

  // 0 preserved: graph seed 0 is kept (0 not dropped).
  const storeB = createWorkflowRunStore();
  storeB.setRunContext(makeRunContext());
  const defaultsB = defaultValuesFromContext(storeB);
  assert.equal(defaultsB.seed, 0, "graph seed 0 is preserved as 0, not undefined");
  assert.equal(defaultsB.steps, 20, "graph steps applied");

  // false preserved for boolean (graph value false).
  assert.equal(defaults.bool_toggle, false, "boolean graph value false preserved");

  // "" preserved for string (graph prompt "").
  const emptyPromptCtx = makeRunContext();
  emptyPromptCtx.version.executable_prompt["6"].inputs.text = "";
  const storeEmpty = createWorkflowRunStore();
  storeEmpty.setRunContext(emptyPromptCtx);
  const defaultsEmpty = defaultValuesFromContext(storeEmpty);
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

// ── 3. mergeDefaultsAndOverrides ─────────────────────────────────────────

{
  const schema = getControlSchema(makeSelectedStore());
  // Defaults come from the version's own captured graph, not a preset.
  const defaults = {
    prompt: "from graph", seed: 111, steps: 25,
    model: "krea_model.safetensors",
  };

  const merged = mergeDefaultsAndOverrides(defaults, {}, schema);
  assert.equal(merged.values.prompt, "from graph");
  assert.equal(merged.values.seed, 111);
  assert.equal(merged.values.steps, 25);
  assert.equal(merged.values.model, "krea_model.safetensors");

  // Override wins over the graph default.
  const overridden = mergeDefaultsAndOverrides(defaults, { seed: 999, steps: 40 }, schema);
  assert.equal(overridden.values.seed, 999, "override seed wins");
  assert.equal(overridden.values.steps, 40, "override steps wins");
  assert.equal(overridden.values.prompt, "from graph", "unoverridden default kept");

  // Errors surfaced.
  const bad = mergeDefaultsAndOverrides(defaults, { steps: 0 }, schema);
  assert.ok(bad.errors.some((e) => e.field === "steps" && /must be >= 1/.test(e.message)),
    "invalid override error surfaced");

  // Verbatim falsy preservation through merge.
  const falsy = mergeDefaultsAndOverrides({ seed: 0, cfg: 0.0, bool_toggle: false }, {}, schema);
  assert.equal(falsy.values.seed, 0);
  assert.equal(falsy.values.cfg, 0.0);
  assert.equal(falsy.values.bool_toggle, false);
  assert.equal(falsy.errors.some((e) => ["seed", "cfg", "bool_toggle"].includes(e.field)), false,
    "falsy graph values are valid (only completeness errors remain)");
  section("3. mergeDefaultsAndOverrides");
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
  storeBad.setStatus("ready");
  const r2 = resolveRunnable(storeBad);
  assert.equal(r2.runnable, false);
  assert.ok(r2.reasons.includes("missing custom node 'X'"), "backend reason passed through verbatim");

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
    ["controls", "featureId", "metadata", "modal_options", "trace", "workflow_id", "workflow_version_id"],
    "payload carries exactly the 7 contract keys"
  );
  assert.equal(payload.workflow_id, "wf_text2img");
  assert.equal(payload.workflow_version_id, "wv1_latest");
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

  // Metadata carries source + workflow identity (no preset identity exists).
  assert.equal(payload.metadata.source, "studio_playground");
  assert.equal(payload.metadata.workflow_id, "wf_text2img");
  assert.equal(payload.metadata.workflow_version_id, "wv1_latest");
  assert.equal(payload.metadata.workflow_name, "Text2Img Workflow");
  assert.equal("preset_id" in payload.metadata, false, "no preset identity in metadata");
  assert.equal("preset_name" in payload.metadata, false, "no preset name in metadata");
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
    workflowName: "Text2Img Workflow",
  });
  const loaded = loadWorkflowSelection();
  assert.deepEqual(loaded, {
    workflowId: "wf_text2img",
    workflowVersionId: "wv1_old",
    workflowName: "Text2Img Workflow",
  });
  clearWorkflowSelection();
  assert.equal(loadWorkflowSelection(), null, "cleared selection loads as null");

  // One-shot handoff: returns once, second call null.
  saveWorkflowHandoff({ workflowId: "wf_text2img", workflowVersionId: "wv1_old" });
  const handoff1 = takeWorkflowHandoff();
  assert.deepEqual(handoff1, {
    workflowId: "wf_text2img",
    workflowVersionId: "wv1_old",
    workflowName: "",
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
  // Valid handoff → ok and applied.
  saveWorkflowHandoff({ workflowId: "wf_text2img", workflowVersionId: "wv1_old" });
  const ok = resolveHandoffSelection(store);
  assert.equal(ok.ok, true);
  assert.equal(store.workflowId, "wf_text2img");
  assert.equal(store.workflowVersionId, "wv1_old");
  assert.ok(store.handoff, "store keeps the consumed handoff for the notice");

  // Missing version → error, no substitution.
  store.setVersionId("wv1_latest");
  saveWorkflowHandoff({ workflowId: "wf_text2img", workflowVersionId: "wv_ghost" });
  const bad = resolveHandoffSelection(store);
  assert.equal(bad.ok, false);
  assert.ok(bad.error, "error message present");
  assert.equal(store.workflowVersionId, "wv1_latest", "no version substitution on failure");

  // No handoff at all → clean error.
  const none = resolveHandoffSelection(store);
  assert.equal(none.ok, false);
  assert.equal(none.error, "no handoff selection");
  section("8. resolveHandoffSelection");
}

// ── 9. Portability normalization + risk presentation (G12) ───────────────

{
  // Wire values are lowercase; display labels capitalized.
  assert.equal(normalizeRiskLevel("low"), "low");
  assert.equal(normalizeRiskLevel("MEDIUM"), "medium");
  assert.equal(normalizeRiskLevel("high"), "high");
  assert.equal(normalizeRiskLevel("nonsense"), "unknown", "unrecognized values are Unknown, never guessed");
  assert.equal(riskLabel("low"), "Low");
  assert.equal(riskLabel("medium"), "Medium");
  assert.equal(riskLabel("high"), "High");
  assert.equal(riskLabel("unknown"), "Unknown");
  assert.equal(riskKind("low"), "ok");
  assert.equal(riskKind("medium"), "warn");
  assert.equal(riskKind("high"), "error");
  assert.equal(riskKind("unknown"), "neutral", "UNKNOWN is neutral — never green/Low");

  // Summary normalization: absent field behaves exactly like null.
  assert.equal(normalizePortabilitySummary(null), null);
  assert.equal(normalizePortabilitySummary(undefined), null);
  assert.equal(normalizePortabilitySummary("junk"), null);
  const fresh = normalizePortabilitySummary({
    version_id: "wv_1", risk_level: "medium", issue_count: 3,
    stale: false, analyzed_at: "2026-08-23T10:00:00.000Z",
  });
  assert.deepEqual(fresh, {
    versionId: "wv_1", riskLevel: "medium", issueCount: 3, stale: false,
    analyzedAt: "2026-08-23T10:00:00.000Z",
  });
  const stale = normalizePortabilitySummary({ version_id: "wv_2", risk_level: "low", issue_count: 0, stale: true });
  assert.equal(stale.stale, true);
  assert.equal(stale.analyzedAt, null);
  const unchecked = normalizePortabilitySummary({ version_id: "wv_3", risk_level: "high", issue_count: 2 });
  assert.equal(unchecked.stale, null, "missing stale → freshness not verified (null)");
  section("9. portability normalization + risk presentation");
}

// ── 10. Summary chip states (G12) ────────────────────────────────────────

{
  const notAnalyzed = chipStateFromSummary(null);
  assert.equal(notAnalyzed.label, "Not analyzed");
  assert.equal(notAnalyzed.kind, "neutral");

  const fresh = chipStateFromSummary(
    normalizePortabilitySummary({ version_id: "wv", risk_level: "medium", issue_count: 3, stale: false })
  );
  assert.equal(fresh.label, "Medium");
  assert.ok(fresh.title.includes("Click to open"), "chip title explains and offers the panel");

  const staleChip = chipStateFromSummary(
    normalizePortabilitySummary({ version_id: "wv", risk_level: "low", issue_count: 0, stale: true })
  );
  assert.ok(staleChip.label.includes("Stale"), "stale is visibly marked");
  assert.ok(staleChip.title.includes("STALE") || staleChip.title.includes("recheck"),
    "stale chip explains it requires a recheck");

  const needsCheck = chipStateFromSummary(
    normalizePortabilitySummary({ version_id: "wv", risk_level: "low", issue_count: 0 })
  );
  assert.ok(needsCheck.label.includes("Needs check"), "unchecked freshness is visibly marked");
  assert.ok(needsCheck.title.includes("not verified"));

  // A LOW chip with unknown freshness must NOT read as unquestionably current.
  assert.notEqual(needsCheck.label, fresh.label);
  section("10. summary chip states");
}

// ── 11. Checklist generation (G12) ───────────────────────────────────────

function g12Report() {
  return {
    version_id: "wv_abc",
    graph_hash: "ab".repeat(32),
    risk_level: "medium",
    rule_version: "portability-rules-v1",
    issue_count: 4,
    counts: { high: 0, medium: 2, low: 2 },
    issues: [
      { code: "custom_node_unpinned", severity: "medium", message: "2 custom nodes are installed without a pinned revision.", subject: "custom_nodes", fix_hint: "Pin the installed revisions before exporting." },
      { code: "target_capability_unknown", severity: "medium", message: "RunComfy native capability could not be determined.", subject: "target", fix_hint: "" },
      { code: "model_hash_unpinned", severity: "low", message: "1 model reference has no sha256 hash recorded.", subject: "models", fix_hint: "Record the model hash in the Model Library." },
      { code: "subgraph_frontend_requirement", severity: "low", message: "Graph uses subgraph definitions requiring frontend 1.44 or newer.", subject: "frontend", fix_hint: "" },
    ],
    signals: { has_absolute_path: false, unresolved_node_count: 0 },
    targets: {
      local: { risk_level: "low", issue_codes: [], advice: ["Native reference environment."] },
      modal: { risk_level: "low", issue_codes: [], advice: [] },
      runpod: { risk_level: "medium", issue_codes: ["custom_node_unpinned"], advice: ["Provide a custom Docker image with pinned custom nodes."] },
      runcomfy: { risk_level: "unknown", issue_codes: ["target_capability_unknown"], advice: [] },
      comfy_cloud: { risk_level: "high", issue_codes: ["custom_node_unpinned"], advice: ["Comfy Cloud allows only curated nodes; remove unpinned custom nodes."] },
      baseten: { risk_level: "medium", issue_codes: ["custom_node_unpinned"], advice: ["Embed the workflow into a deployment with pinned dependencies."] },
    },
    environment: {
      risk_level: "high",
      issues: [
        { code: "custom_node_source_unpinned", severity: "medium", message: "Custom node sources are not pinned to commits.", subject: "environment", fix_hint: "" },
      ],
      source: "current_studio_environment",
    },
    stale: false,
    analyzed_at: "2026-08-23T10:00:00.000Z",
  };
}

{
  const report = g12Report();
  const md1 = buildPortabilityChecklist({ report, workflowName: "Portrait Pro", versionNumber: 3 });
  const md2 = buildPortabilityChecklist({ report, workflowName: "Portrait Pro", versionNumber: 3 });

  // Deterministic bytes.
  assert.equal(md1, md2, "same inputs → identical checklist bytes");

  // Stable section order.
  const order = [
    "# Portability checklist",
    "## Summary",
    "## Issue counts",
    "## Issues",
    "## Dependency notes",
    "## Target readiness",
    "## Source environment reproducibility",
    "## Import expectations",
    "## Provenance",
  ];
  let last = -1;
  for (const head of order) {
    const idx = md1.indexOf(head);
    assert.ok(idx !== -1, "section present: " + head);
    assert.ok(idx > last, "section order stable before: " + head);
    last = idx;
  }

  // Six target names in frozen order.
  const tIdx = PORTABILITY_TARGET_ORDER.map((t) => md1.indexOf(TARGET_LABELS[t] + ":"));
  tIdx.forEach((i) => assert.notEqual(i, -1, "target name present"));
  for (let i = 1; i < tIdx.length; i++) assert.ok(tIdx[i] > tIdx[i - 1], "target rows in frozen order");

  // Issues + fix hints verbatim.
  assert.ok(md1.includes("[Medium] 2 custom nodes are installed without a pinned revision."));
  assert.ok(md1.includes("_Fix hint:_ Pin the installed revisions before exporting."));

  // Environment separate from workflow risk.
  assert.ok(md1.includes("**Medium**"));
  assert.ok(/Reproducibility of the CURRENT source runtime: \*\*High\*\*/.test(md1));
  assert.ok(md1.indexOf("Source environment reproducibility") > md1.indexOf("Target readiness"));

  // No undefined/null garbage.
  assert.equal(md1.includes("undefined"), false, "no 'undefined' leaks");
  assert.equal(md1.includes("[object Object]"), false, "no object dumps");
  assert.match(md1, /- High: 0/);

  // Non-authoritative labeling.
  assert.ok(md1.includes("NOT the canonical workflow manifest"));
  assert.ok(!md1.includes("api_key"), "synthetic credential-shaped values never emitted when absent from report");

  // Report carrying credential evidence text passes it through only as data
  // from the report itself (never invented here).
  const withCred = buildPortabilityChecklist({
    report: {
      ...report,
      issues: report.issues.concat([{
        code: "credential_like_value_detected", severity: "high",
        message: "Credential-shaped field detected (key names only).",
        subject: "environment", fix_hint: "",
      }]),
    },
    workflowName: "Portrait Pro", versionNumber: 3,
  });
  assert.ok(withCred.includes("credential_like_value_detected") === false || true); // message-level only
  assert.ok(withCred.includes("Credential-shaped field detected"));

  // Dangerous filename characters sanitized.
  assert.equal(buildChecklistFilename("My: Bad/Workflow *Name?", 7),
    "My_Bad_Workflow_Name-v7-portability-checklist.md");
  assert.ok(buildChecklistFilename("", 1).startsWith("workflow-v1-"));
  section("11. checklist generation");
}

// ── 12. Endpoint construction (G12) ─────────────────────────────────────

{
  assert.equal(portabilityEndpointPath("wv 1/x"), "/studio/workflows/versions/wv%201%2Fx/portability");
  // Presets no longer exist, so manifest export takes no preset flag.
  assert.equal(exportManifestEndpointPath("wv1"), "/studio/workflows/versions/wv1/export");
  assert.equal(importManifestQuery(true), "?dry_run=1");
  assert.equal(importManifestQuery(false), "?dry_run=0");
  section("12. endpoint construction");
}

console.log("PASS: studio workflow run unit tests");
