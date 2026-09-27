import assert from "node:assert/strict";
import {
  BINDABLE_INPUTS,
  OUTPUT_BINDING,
  T2I_REQUIRED_INPUTS,
  T2I_OPTIONAL_INPUTS,
  getWorkflowInputKeys,
  listBindableInputs,
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
  assert.deepEqual(keys, ["prompt", "seed", "step_count", "cfg_scale", "sampler", "model_unet", "vae", "clip"]);
  assert.deepEqual(keys.map((key) => BINDABLE_INPUTS[key].name), [
    "Prompt", "Seed", "Step count", "CFG scale", "Sampler", "Model UNET", "VAE", "CLIP",
  ]);
  assert.equal(Object.prototype.hasOwnProperty.call(BINDABLE_INPUTS, "output"), false);
  assert.deepEqual(T2I_REQUIRED_INPUTS, ["prompt", "seed", "model_unet", "vae", "clip"]);
  assert.deepEqual(T2I_OPTIONAL_INPUTS, ["step_count", "cfg_scale", "sampler"]);
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

checkCatalog();
if (process.argv.includes("--render")) checkBlocksRender();
