import assert from "node:assert/strict";
import {
  BINDABLE_INPUTS,
  OUTPUT_BINDING,
  REFERENCE_METHODS,
  REFERENCE_METHOD_IDS,
  T2I_REQUIRED_INPUTS,
  T2I_OPTIONAL_INPUTS,
  applyReferenceConfirmation,
  buildReferencePayload,
  getReferenceMethod,
  getWorkflowInputKeys,
  isReferenceSelectionValid,
  listBindableInputs,
  listReferenceMethods,
} from "../web/studio-bindable-inputs.js";
import {
  FIELD_BLOCKS,
  INTEGER_RULES,
  renderFieldBlock,
} from "../web/studio-field-blocks.js";

function makeDocument() {
  function node(tag) {
    const item = {
      tagName: String(tag).toUpperCase(),
      children: [],
      attributes: {},
      listeners: {},
      dataset: {},
      value: "",
      appendChild(child) { this.children.push(child); return child; },
      addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); },
      setAttribute(name, value) {
        this.attributes[name] = String(value);
        if (name === "data-testid") this.dataset.testid = String(value);
      },
    };
    return item;
  }
  return {
    createElement: node,
    createTextNode(text) { return { textContent: String(text) }; },
  };
}

function checkCatalog() {
  const keys = Object.keys(BINDABLE_INPUTS);
  assert.deepEqual(keys, ["prompt", "seed", "step_count", "cfg_scale", "sampler", "width", "height", "model_unet", "vae", "clip", "source_image", "mask"]);
  assert.deepEqual(keys.map((key) => BINDABLE_INPUTS[key].name), [
    "Prompt", "Seed", "Step count", "CFG scale", "Sampler", "Width", "Height", "Model UNET", "VAE", "CLIP", "Source Image", "Mask",
  ]);
  assert.equal(Object.prototype.hasOwnProperty.call(BINDABLE_INPUTS, "output"), false);
  assert.deepEqual(T2I_REQUIRED_INPUTS, ["prompt", "seed", "model_unet", "vae", "clip"]);
  assert.deepEqual(T2I_OPTIONAL_INPUTS, ["step_count", "cfg_scale", "sampler", "width", "height"]);
  assert.deepEqual(getWorkflowInputKeys("t2i", true), T2I_REQUIRED_INPUTS);
  assert.deepEqual(getWorkflowInputKeys("t2i", false), T2I_OPTIONAL_INPUTS);
  assert.equal(OUTPUT_BINDING.block, null);
  assert.equal(OUTPUT_BINDING.binding.kind, "output");
  assert.equal(OUTPUT_BINDING.binding.exact, true);

  for (const entry of listBindableInputs()) {
    assert.equal(typeof entry.key, "string");
    assert.equal(entry.blockDefinition.inputKind, entry.inputKind);
    assert.equal(entry.blockKind, entry.block);
    assert.equal(entry.binding.exact, true);
    assert.equal(entry.binding.cardinality, "one");
    assert.equal(entry.binding.kind, "widget");
    assert.equal(Array.isArray(entry.requiredFor), true);
    assert.equal(Array.isArray(entry.optionalFor), true);
  }
  assert.equal(BINDABLE_INPUTS.seed.rules.allowNegative, true);
  assert.equal(BINDABLE_INPUTS.seed.rules.minimum, null);
  assert.equal(INTEGER_RULES.nonNegative.minimum, 0);
  assert.equal(INTEGER_RULES.nonNegative.allowNegative, false);
  console.log("BINDABLE_INPUTS_PASS");
}

function checkBlocksRender() {
  globalThis.document = makeDocument();
  const values = {
    multiline: { value: "a prompt" },
    integer: { value: -12, rules: INTEGER_RULES.seed },
    float: { value: 7.5 },
    dropdown: { value: "euler", options: ["euler", "ddim"] },
    "model-picker": { value: "model.safetensors", models: ["model.safetensors"] },
  };
  for (const [kind, definition] of Object.entries(FIELD_BLOCKS)) {
    const rendered = renderFieldBlock(kind, values[kind]);
    assert.ok(rendered, kind + " block rendered");
    assert.equal(rendered.attributes["data-field-kind"], definition.inputKind === "model" ? "model" : kind);
  }
  const seed = renderFieldBlock("integer", { value: -5, rules: INTEGER_RULES.seed });
  assert.equal(seed.value, "-5");
  assert.equal(seed.attributes.min, undefined);
  console.log("BLOCK_RENDER_PASS");
}

function checkReferenceMethods() {
  // Frozen method ids: the wizard, Mapping records, and the
  // `studio_references` run companion key on these exact strings.
  assert.deepEqual(REFERENCE_METHOD_IDS, ["conditioning_slots", "reference_latent_chain", "dedicated"]);
  assert.deepEqual(Object.keys(REFERENCE_METHODS), [...REFERENCE_METHOD_IDS]);
  for (const method of listReferenceMethods()) {
    assert.equal(typeof method.key, "string");
    assert.equal(typeof method.name, "string");
    assert.equal(getReferenceMethod(method.key), method);
  }
  assert.equal(getReferenceMethod("nope"), null);
  assert.equal(Object.prototype.hasOwnProperty.call(BINDABLE_INPUTS, "conditioning_slots"), false);
  console.log("REFERENCE_METHODS_PASS");
}

function checkReferenceSelection() {
  const candidates = {
    candidates: [
      {
        candidate_id: "conditioning_slots:3",
        method: "conditioning_slots",
        node_id: "3",
        compatible: true,
        slots: [
          { node_id: "3", socket: "image_1", order: 0, kind: "source" },
          { node_id: "3", socket: "image_2", order: 1, kind: "reference" },
        ],
        slot_order: ["image_1", "image_2"],
        capacity: { kind: "fixed", reference_writable: 1 },
      },
      {
        candidate_id: "reference_latent_chain:10",
        method: "reference_latent_chain",
        node_id: "10",
        compatible: true,
        chain: {
          loader_node_id: "7",
          vae_encode_node_id: "9",
          reference_latent_node_id: "10",
          order: ["7", "9", "10"],
        },
      },
    ],
    resolution: "unresolved",
  };

  // Opt-out wizards always validate (untouched saves behave as before).
  assert.equal(isReferenceSelectionValid(null), true);
  assert.equal(isReferenceSelectionValid({}), true);
  assert.equal(isReferenceSelectionValid({ referenceEnabled: false }), true);

  // Unconfirmed multi-candidate state blocks the save gate.
  const pending = { referenceEnabled: true, referenceCandidates: candidates };
  assert.equal(isReferenceSelectionValid(pending), false);
  assert.equal(buildReferencePayload(pending), null);

  // Explicit confirmation resolves one candidate with order + capacity.
  assert.equal(applyReferenceConfirmation(pending, "conditioning_slots:3", "conditioning_slots"), true);
  assert.equal(pending.referenceMethod, "conditioning_slots");
  assert.equal(isReferenceSelectionValid(pending), true);
  const payload = buildReferencePayload(pending);
  assert.equal(payload.reference_method, "conditioning_slots");
  assert.equal(payload.reference_bindings.candidate_id, "conditioning_slots:3");
  assert.deepEqual(payload.reference_bindings.slots.map((s) => s.order), [0, 1]);
  assert.equal(payload.reference_bindings.slots[0].kind, "source");

  // Method-2 confirmation carries the chain boundary.
  const chainState = { referenceEnabled: true, referenceCandidates: candidates };
  assert.equal(applyReferenceConfirmation(chainState, "reference_latent_chain:10"), true);
  assert.equal(isReferenceSelectionValid(chainState), true);
  assert.equal(buildReferencePayload(chainState).reference_bindings.chain.reference_latent_node_id, "10");

  // Unknown candidates never confirm.
  assert.equal(applyReferenceConfirmation({ referenceCandidates: candidates }, "nope"), false);
  console.log("REFERENCE_SELECTION_PASS");
}

checkCatalog();
checkReferenceMethods();
checkReferenceSelection();
if (process.argv.includes("--render")) checkBlocksRender();
