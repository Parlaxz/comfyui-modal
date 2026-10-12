// Modal Studio — code-owned bindable input catalog.
//
// This is deliberately a small product vocabulary, not a node editor.  A
// workflow may contain many graph fields, but only entries in this catalog can
// become Studio inputs.  The graph binding selected by the workflow wizard is
// one exact target; this catalog supplies the semantic name, block, and fixed
// value rules for that target.

import { FIELD_BLOCKS, INTEGER_RULES } from "./studio-field-blocks.js";

const exactWidgetBinding = Object.freeze({
  kind: "widget",
  exact: true,
  cardinality: "one",
});

function input(definition) {
  return Object.freeze({
    ...definition,
    binding: Object.freeze({ ...exactWidgetBinding }),
    blockKind: definition.block,
    blockDefinition: FIELD_BLOCKS[definition.block],
  });
}

// The names and order here are product API.  Add a new entry for a new
// capability; do not expose a user-defined field type or rename these keys.
// Tool Inputs: a Prompt is a Prompt across every workflow type; the workflow
// type decides whether a given Tool Input is required/optional.
const IMAGE_TYPES = Object.freeze(["t2i", "i2i", "inpaint", "sketch", "outpaint"]);
export const BINDABLE_INPUTS = Object.freeze({
  prompt: input({
    key: "prompt",
    name: "Prompt",
    block: "multiline",
    inputKind: "multiline",
    requiredFor: [...IMAGE_TYPES],
    optionalFor: [],
    experimentEligible: true,
    rules: Object.freeze({ multiline: true }),
  }),
  seed: input({
    key: "seed",
    name: "Seed",
    block: "integer",
    inputKind: "integer",
    requiredFor: [...IMAGE_TYPES],
    optionalFor: [],
    experimentEligible: true,
    rules: INTEGER_RULES.seed,
  }),
  step_count: input({
    key: "step_count",
    name: "Step count",
    block: "integer",
    inputKind: "integer",
    requiredFor: [],
    optionalFor: [...IMAGE_TYPES],
    experimentEligible: true,
    rules: Object.freeze({ minimum: 1, step: 1, allowNegative: false }),
  }),
  cfg_scale: input({
    key: "cfg_scale",
    name: "CFG scale",
    block: "float",
    inputKind: "float",
    requiredFor: [],
    optionalFor: [...IMAGE_TYPES],
    experimentEligible: true,
    rules: Object.freeze({ minimum: 0, step: "any" }),
  }),
  sampler: input({
    key: "sampler",
    name: "Sampler",
    block: "dropdown",
    inputKind: "dropdown",
    requiredFor: [],
    optionalFor: [...IMAGE_TYPES],
    experimentEligible: true,
    rules: Object.freeze({}),
  }),
  width: input({
    key: "width",
    name: "Width",
    block: "integer",
    inputKind: "integer",
    requiredFor: [],
    optionalFor: [...IMAGE_TYPES],
    experimentEligible: true,
    rules: Object.freeze({ minimum: 64, maximum: 4096, step: 8, allowNegative: false }),
  }),
  height: input({
    key: "height",
    name: "Height",
    block: "integer",
    inputKind: "integer",
    requiredFor: [],
    optionalFor: [...IMAGE_TYPES],
    experimentEligible: true,
    rules: Object.freeze({ minimum: 64, maximum: 4096, step: 8, allowNegative: false }),
  }),
  model_unet: input({
    key: "model_unet",
    name: "Model UNET",
    block: "model-picker",
    inputKind: "model",
    requiredFor: [...IMAGE_TYPES],
    optionalFor: [],
    experimentEligible: true,
    rules: Object.freeze({ modelType: "unet" }),
  }),
  vae: input({
    key: "vae",
    name: "VAE",
    block: "model-picker",
    inputKind: "model",
    requiredFor: [...IMAGE_TYPES],
    optionalFor: [],
    experimentEligible: true,
    rules: Object.freeze({ modelType: "vae" }),
  }),
  clip: input({
    key: "clip",
    name: "CLIP",
    block: "model-picker",
    inputKind: "model",
    requiredFor: [...IMAGE_TYPES],
    optionalFor: [],
    experimentEligible: true,
    rules: Object.freeze({ modelType: "clip" }),
  }),
  source_image: input({
    key: "source_image",
    name: "Source Image",
    block: "image",
    inputKind: "image",
    requiredFor: ["i2i", "inpaint", "sketch", "outpaint"],
    optionalFor: [],
    experimentEligible: false,
    rules: Object.freeze({}),
  }),
  mask: input({
    key: "mask",
    name: "Mask",
    block: "image",
    inputKind: "image",
    requiredFor: ["inpaint"],
    optionalFor: ["sketch", "outpaint"],
    experimentEligible: false,
    rules: Object.freeze({}),
  }),
});

// Output is intentionally not in BINDABLE_INPUTS and has no Playground block.
// It is the one required result binding consumed by the output panel.
export const OUTPUT_BINDING = Object.freeze({
  key: "output",
  name: "Output",
  binding: Object.freeze({
    kind: "output",
    exact: true,
    cardinality: "one",
  }),
  requiredFor: [...IMAGE_TYPES],
  block: null,
});

export const WORKFLOW_TYPES = IMAGE_TYPES;

const WORKFLOW_TYPE_ALIASES = Object.freeze({
  txt2img: "t2i",
  text_to_image: "t2i",
  img2img: "i2i",
  image_to_image: "i2i",
  image_edit: "i2i",
});

export function normalizeWorkflowType(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return "t2i";
  return WORKFLOW_TYPE_ALIASES[raw] || raw;
}

export const T2I_REQUIRED_INPUTS = Object.freeze([
  "prompt",
  "seed",
  "model_unet",
  "vae",
  "clip",
]);

export const T2I_OPTIONAL_INPUTS = Object.freeze([
  "step_count",
  "cfg_scale",
  "sampler",
  "width",
  "height",
]);

export const I2I_REQUIRED_INPUTS = Object.freeze([
  "prompt",
  "seed",
  "model_unet",
  "vae",
  "clip",
  "source_image",
]);

export const I2I_OPTIONAL_INPUTS = Object.freeze([
  "step_count",
  "cfg_scale",
  "sampler",
  "width",
  "height",
]);

export const INPAINT_REQUIRED_INPUTS = Object.freeze([
  "prompt",
  "seed",
  "model_unet",
  "vae",
  "clip",
  "source_image",
  "mask",
]);

export const INPAINT_OPTIONAL_INPUTS = Object.freeze([
  "step_count",
  "cfg_scale",
  "sampler",
  "width",
  "height",
]);

export const SKETCH_REQUIRED_INPUTS = Object.freeze([
  "prompt",
  "seed",
  "model_unet",
  "vae",
  "clip",
  "source_image",
]);

export const SKETCH_OPTIONAL_INPUTS = Object.freeze([
  "step_count",
  "cfg_scale",
  "sampler",
  "width",
  "height",
  "mask",
]);

export const OUTPAINT_REQUIRED_INPUTS = Object.freeze([
  "prompt",
  "seed",
  "model_unet",
  "vae",
  "clip",
  "source_image",
]);

export const OUTPAINT_OPTIONAL_INPUTS = Object.freeze([
  "step_count",
  "cfg_scale",
  "sampler",
  "width",
  "height",
  "mask",
]);

export function getBindableInput(key) {
  return BINDABLE_INPUTS[key] || null;
}

export function listBindableInputs() {
  return Object.keys(BINDABLE_INPUTS).map((key) => BINDABLE_INPUTS[key]);
}

export function getWorkflowInputKeys(workflowType, required) {
  const type = normalizeWorkflowType(workflowType || "t2i");
  return listBindableInputs()
    .filter((entry) => (required ? entry.requiredFor : entry.optionalFor).includes(type))
    .map((entry) => entry.key);
}
