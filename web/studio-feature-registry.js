// Modal Studio — Feature Registry
//
// Defines Studio features and their controls. Drives Playground rendering.
// Each control definition includes id, label, type, defaultValue, numeric
// constraints, experimentEligible flag, feature applicability, and help text.

export const FEATURE_SPECS = [
  {
    id: "txt2img",
    label: "Txt2Img",
    description: "Text-to-image generation with full control over parameters.",
    supportsImageCanvas: false,
    controls: ["prompt", "negative_prompt", "steps", "guidance", "denoise", "seed", "width", "height", "sampler", "scheduler", "lora", "lora_strength", "mask_blur", "mask_expand"],
  },
  {
    id: "object_remove",
    label: "Object Remove",
    description: "Remove objects from images using AI-powered selection and inpainting.",
    supportsImageCanvas: true,
    futureTools: ["SAM click selection", "Text object selection", "Brush refine"],
    isPlaceholder: true,
    placeholderReason: "Image-edit tools are not implemented in this release. Use Settings > Legacy Setup for the full experiment suite.",
    controls: ["prompt", "instruction", "steps", "guidance", "denoise", "seed", "lora", "lora_strength", "mask_blur", "mask_expand"],
  },
  {
    id: "object_replace",
    label: "Object Replace",
    description: "Replace objects in images with AI-generated content using reference images or prompts.",
    supportsImageCanvas: true,
    futureTools: ["SAM click selection", "Text object selection", "Reference image"],
    isPlaceholder: true,
    placeholderReason: "Image-edit tools are not implemented in this release. Use Settings > Legacy Setup for the full experiment suite.",
    controls: ["prompt", "instruction", "steps", "guidance", "denoise", "seed", "lora", "lora_strength", "mask_blur", "mask_expand"],
  },
];

export const CONTROL_DEFS = {
  prompt: {
    id: "prompt",
    label: "Prompt",
    type: "textarea",
    defaultValue: "",
    placeholder: "Describe what you want to generate\u2026",
    experimentEligible: true,
    helpText: "The main prompt describing the desired output.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  negative_prompt: {
    id: "negative_prompt",
    label: "Negative Prompt",
    type: "textarea",
    defaultValue: "",
    placeholder: "Describe what to avoid\u2026",
    experimentEligible: true,
    helpText: "Things to exclude from the generated output.",
    applicableFeatures: ["txt2img"],
  },
  instruction: {
    id: "instruction",
    label: "Instruction",
    type: "textarea",
    defaultValue: "",
    placeholder: "Describe the edit you want to perform\u2026",
    experimentEligible: true,
    helpText: "Natural language instruction for the image edit.",
    applicableFeatures: ["object_remove", "object_replace"],
  },
  steps: {
    id: "steps",
    label: "Steps",
    type: "number",
    defaultValue: 20,
    min: 1,
    max: 150,
    step: 1,
    experimentEligible: true,
    helpText: "Number of sampling steps. Higher values may improve quality at the cost of speed.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  guidance: {
    id: "guidance",
    label: "Guidance (CFG)",
    type: "number",
    defaultValue: 7.0,
    min: 1.0,
    max: 30.0,
    step: 0.5,
    experimentEligible: true,
    helpText: "Classifier-free guidance scale. Higher values follow the prompt more closely.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  denoise: {
    id: "denoise",
    label: "Denoise",
    type: "number",
    defaultValue: 1.0,
    min: 0.0,
    max: 1.0,
    step: 0.05,
    experimentEligible: true,
    helpText: "Denoising strength. 1.0 = full generation, lower = less change from input.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  width: {
    id: "width",
    label: "Width",
    type: "number",
    defaultValue: 1024,
    min: 64,
    max: 4096,
    step: 8,
    experimentEligible: true,
    helpText: "Output image width in pixels. Must be a multiple of 8.",
    applicableFeatures: ["txt2img"],
  },
  height: {
    id: "height",
    label: "Height",
    type: "number",
    defaultValue: 1024,
    min: 64,
    max: 4096,
    step: 8,
    experimentEligible: true,
    helpText: "Output image height in pixels. Must be a multiple of 8.",
    applicableFeatures: ["txt2img"],
  },
  seed: {
    id: "seed",
    label: "Seed",
    type: "number",
    defaultValue: -1,
    min: -1,
    max: 2147483647,
    step: 1,
    experimentEligible: true,
    helpText: "Random seed for reproducibility. -1 = random.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  sampler: {
    id: "sampler",
    label: "Sampler",
    type: "select",
    defaultValue: "euler",
    experimentEligible: true,
    dynamicOptions: true,
    helpText: "Sampler name for the generation. Options come from the backend preset's graph schema.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  scheduler: {
    id: "scheduler",
    label: "Scheduler",
    type: "select",
    defaultValue: "normal",
    experimentEligible: true,
    dynamicOptions: true,
    helpText: "Scheduler name for the generation. Options come from the backend preset's graph schema.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  lora: {
    id: "lora",
    label: "LoRA",
    type: "select",
    defaultValue: "",
    experimentEligible: false,
    helpText: "LoRA model to apply. Configured in Settings > Legacy Setup.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  lora_strength: {
    id: "lora_strength",
    label: "LoRA Strength",
    type: "number",
    defaultValue: 1.0,
    min: 0.0,
    max: 2.0,
    step: 0.05,
    experimentEligible: true,
    helpText: "Strength of the applied LoRA. 1.0 = default.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  mask_blur: {
    id: "mask_blur",
    label: "Mask Blur",
    type: "number",
    defaultValue: 4,
    min: 0,
    max: 64,
    step: 1,
    experimentEligible: true,
    helpText: "Blur radius applied to the inpaint mask edges.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
  mask_expand: {
    id: "mask_expand",
    label: "Mask Expand",
    type: "number",
    defaultValue: 0,
    min: -64,
    max: 64,
    step: 1,
    experimentEligible: true,
    helpText: "Expand (positive) or contract (negative) the inpaint mask.",
    applicableFeatures: ["txt2img", "object_remove", "object_replace"],
  },
};

// ── Shared Steps recommendation ──────────────────────────────────────────
//
// Workflow/preset-backed "recommended steps" available before runs.
// Sources, most trustworthy first:
//   1. A freshly captured workflow run config for the CURRENT selection
//      (state.playground._runningExperimentConfig) — only trusted when the
//      captured preset/feature match the current selection.
//   2. The selected preset's workflow-captured default
//      (state.playground._currentPreset.defaults.steps).
// Values outside the steps schema range are never trusted.  Returns null
// when no trustworthy source exists so callers can hide the action.

export function getRecommendedSteps(state) {
  const pg = state && state.playground;
  if (!pg) return null;
  const def = CONTROL_DEFS.steps;
  const min = def && def.min != null ? def.min : 1;
  const max = def && def.max != null ? def.max : 150;
  function _valid(v) {
    const n = Number(v);
    return !isNaN(n) && isFinite(n) && n >= min && n <= max;
  }

  const cfg = pg._runningExperimentConfig;
  if (cfg && cfg.controls && cfg.controls.steps != null && _valid(cfg.controls.steps)) {
    const cfgPresetId = Array.isArray(cfg.presetIds) && cfg.presetIds.length > 0 ? cfg.presetIds[0] : null;
    const presetMatches = !cfgPresetId || cfgPresetId === pg.selectedBackendId;
    const featureMatches = !cfg.featureId || cfg.featureId === (pg.featureId || "txt2img");
    if (presetMatches && featureMatches) return Number(cfg.controls.steps);
  }

  const preset = pg._currentPreset;
  if (preset && preset.defaults && preset.defaults.steps != null && _valid(preset.defaults.steps)) {
    return Number(preset.defaults.steps);
  }
  return null;
}

/**
 * Status for the recommended-steps action.
 * @returns {{value:number|null, reason:string}} reason is non-empty when
 *   the action should be disabled (applying would change nothing).
 */
export function getRecommendedStepsStatus(state, currentValues) {
  const value = getRecommendedSteps(state);
  if (value == null) return { value: null, reason: "" };
  if (Array.isArray(currentValues) && currentValues.length > 0) {
    const allEqual = currentValues.every(function (v) {
      return String(v) === String(value);
    });
    if (allEqual) return { value: value, reason: "Already applied" };
  }
  return { value: value, reason: "" };
}

// ── Seed insertion helpers ───────────────────────────────────────────────

/** Last finite numeric value in the list (scanning from the end), or null. */
export function getLastFiniteSeed(values) {
  if (!Array.isArray(values)) return null;
  for (var i = values.length - 1; i >= 0; i--) {
    if (values[i] === "" || values[i] == null) continue;
    var n = Number(values[i]);
    if (!isNaN(n) && isFinite(n)) return n;
  }
  return null;
}

/** CSPRNG integer in [0, max] via crypto.getRandomValues. */
export function cryptoRandomSeed(max) {
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    var buf = new Uint32Array(1);
    crypto.getRandomValues(buf);
    return Math.floor((buf[0] / 4294967296) * (max + 1));
  }
  return Math.floor(Math.random() * (max + 1));
}
