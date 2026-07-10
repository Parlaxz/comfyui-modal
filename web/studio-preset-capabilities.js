// Modal Studio — Preset Capability Layer
//
// Pure functions that determine which controls are available/bound/visible
// for a given preset, snapshot, or feature. No side effects, no class,
// no imports from composition/backend modules — only static defs.
//
// Every function accepts a preset-like object (preset or snapshot) with:
//   compatibleFeatures: string[]
//   nodeBindings: { [bindingKey]: { nodeId, kind, nodeType, ... } }
//   status: string              // server-derived
//   disabledReason: string      // server-derived
//   apiPromptJson: object|null
//   graphJson: object|null
//

// ── Feature Requirements ─────────────────────────────────────────────────
//
// Each feature lists required binding keys, optional binding keys, and
// API-graph requirements.  orderRequired groups represent alternatives
// (at least one binding from the group must exist).

export const FEATURE_REQUIREMENTS = {
  txt2img: {
    requiredBindingKeys: ["prompt", "output"],
    optionalBindingKeys: [
      "negative_prompt", "steps", "guidance", "denoise", "seed",
      "sampler", "scheduler", "width", "height",
      "lora", "lora_strength", "model", "vae",
    ],
    needsApiGraph: true,
  },
  object_remove: {
    requiredBindingKeys: ["source_image", "mask", "output"],
    // At least one binding from each sub-array must exist
    orRequiredBindingKeys: [["instruction", "prompt"]],
    optionalBindingKeys: [
      "steps", "guidance", "denoise", "seed",
      "mask_blur", "mask_expand",
      "sampler", "scheduler", "lora", "lora_strength",
    ],
    needsApiGraph: true,
  },
  object_replace: {
    requiredBindingKeys: ["source_image", "mask", "output"],
    orRequiredBindingKeys: [["replacement_prompt", "instruction"]],
    optionalBindingKeys: [
      "reference_image", "steps", "guidance", "denoise", "seed",
      "mask_blur", "mask_expand",
      "sampler", "scheduler", "lora", "lora_strength",
    ],
    needsApiGraph: true,
  },
};

// ── Control-Binding Metadata ─────────────────────────────────────────────
//
// Full key → def map.  `isControl: false` marks internal/pipeline bindings
// that have no corresponding Playground control row.

export const CONTROL_BINDING_DEFS = {
  prompt: {
    key: "prompt",
    label: "Prompt",
    type: "textarea",
    isControl: true,
    experimentEligible: true,
    helpText: "The text prompt widget/input defining the desired output.",
  },
  output: {
    key: "output",
    label: "Output Image",
    type: "output",
    isControl: false,
    experimentEligible: false,
    helpText: "The image output node that produces the result.",
  },
  negative_prompt: {
    key: "negative_prompt",
    label: "Negative Prompt",
    type: "textarea",
    isControl: true,
    experimentEligible: true,
    helpText: "Things to exclude from the generated output.",
  },
  instruction: {
    key: "instruction",
    label: "Instruction",
    type: "textarea",
    isControl: true,
    experimentEligible: true,
    helpText: "Natural language instruction for the image edit.",
  },
  replacement_prompt: {
    key: "replacement_prompt",
    label: "Replacement Prompt",
    type: "textarea",
    isControl: true,
    experimentEligible: true,
    helpText: "Prompt describing what to replace the object with.",
  },
  source_image: {
    key: "source_image",
    label: "Source Image",
    type: "image",
    isControl: false,
    experimentEligible: false,
    helpText: "Input image node providing the source.",
  },
  mask: {
    key: "mask",
    label: "Mask",
    type: "image",
    isControl: false,
    experimentEligible: false,
    helpText: "Mask node indicating the region to edit.",
  },
  reference_image: {
    key: "reference_image",
    label: "Reference Image",
    type: "image",
    isControl: false,
    experimentEligible: false,
    helpText: "Optional reference image for replacement guidance.",
  },
  steps: {
    key: "steps",
    label: "Steps",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Number of sampling steps.",
  },
  guidance: {
    key: "guidance",
    label: "Guidance (CFG)",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Classifier-free guidance scale.",
  },
  denoise: {
    key: "denoise",
    label: "Denoise",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Denoising strength.",
  },
  seed: {
    key: "seed",
    label: "Seed",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Random seed for reproducibility.",
  },
  sampler: {
    key: "sampler",
    label: "Sampler",
    type: "select",
    isControl: true,
    experimentEligible: false,
    helpText: "Sampler name.",
  },
  scheduler: {
    key: "scheduler",
    label: "Scheduler",
    type: "select",
    isControl: true,
    experimentEligible: false,
    helpText: "Scheduler name.",
  },
  width: {
    key: "width",
    label: "Width",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Output image width.",
  },
  height: {
    key: "height",
    label: "Height",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Output image height.",
  },
  lora: {
    key: "lora",
    label: "LoRA",
    type: "select",
    isControl: true,
    experimentEligible: false,
    helpText: "LoRA model to apply.",
  },
  lora_strength: {
    key: "lora_strength",
    label: "LoRA Strength",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Strength of the applied LoRA.",
  },
  model: {
    key: "model",
    label: "Model",
    type: "select",
    isControl: true,
    experimentEligible: false,
    helpText: "Base checkpoint model.",
  },
  vae: {
    key: "vae",
    label: "VAE",
    type: "select",
    isControl: true,
    experimentEligible: false,
    helpText: "VAE model.",
  },
  mask_blur: {
    key: "mask_blur",
    label: "Mask Blur",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Blur radius applied to the mask edges.",
  },
  mask_expand: {
    key: "mask_expand",
    label: "Mask Expand",
    type: "number",
    isControl: true,
    experimentEligible: true,
    helpText: "Expand (positive) or contract (negative) the mask.",
  },
};

// ── Control-to-Binding-Key Resolution ────────────────────────────────────
//
// Some controls (e.g. "instruction") can be satisfied by multiple binding
// keys depending on the feature.  Returns the binding key(s) to check.

function _getBindingKeysForControl(controlId, featureId) {
  // Direct 1:1 mapping for most controls
  if (controlId !== "instruction") return [controlId];
  // "instruction" control can be satisfied by either instruction or
  // replacement_prompt key, depending on which binding exists
  if (featureId === "object_replace") return ["replacement_prompt", "instruction"];
  if (featureId === "object_remove") return ["instruction", "prompt"];
  return ["instruction"];
}

function _isBound(presetOrSnapshot, bindingKey) {
  if (!presetOrSnapshot) return false;
  const bindings = presetOrSnapshot.nodeBindings || {};
  const val = bindings[bindingKey];
  return !!(val && val.nodeId);
}

function _isAnyBound(presetOrSnapshot, bindingKeys) {
  return bindingKeys.some((k) => _isBound(presetOrSnapshot, k));
}

// ── Pure Query Functions ─────────────────────────────────────────────────

/** Required binding definitions for a feature (including or-required groups). */
export function getRequiredBindingsForFeature(featureId) {
  const req = FEATURE_REQUIREMENTS[featureId];
  if (!req) return [];
  const defs = req.requiredBindingKeys
    .map((k) => CONTROL_BINDING_DEFS[k])
    .filter(Boolean);
  // or-required groups: return first alternative from each group as the
  // "representative" def; callers use getMissingRequiredBindings for truth.
  if (req.orRequiredBindingKeys) {
    req.orRequiredBindingKeys.forEach((group) => {
      const first = CONTROL_BINDING_DEFS[group[0]];
      if (first) defs.push(first);
    });
  }
  return defs;
}

/** Optional binding definitions for a feature. */
export function getOptionalBindingsForFeature(featureId) {
  const req = FEATURE_REQUIREMENTS[featureId];
  if (!req) return [];
  return req.optionalBindingKeys
    .map((k) => CONTROL_BINDING_DEFS[k])
    .filter(Boolean);
}

/** All binding definitions relevant to a feature (required + optional). */
export function getAllBindingDefsForFeature(featureId) {
  return [
    ...getRequiredBindingsForFeature(featureId),
    ...getOptionalBindingsForFeature(featureId),
  ];
}

/** Binding keys that have a valid nodeId binding in this preset/snapshot. */
export function getBoundControlIds(presetOrSnapshot) {
  if (!presetOrSnapshot) return [];
  const bindings = presetOrSnapshot.nodeBindings || {};
  return Object.entries(bindings)
    .filter(([, v]) => v && v.nodeId)
    .map(([k]) => k);
}

/** True if the given control has a valid binding in this preset/snapshot. */
export function isControlBound(presetOrSnapshot, controlId, featureId) {
  const keys = _getBindingKeysForControl(controlId, featureId);
  return _isAnyBound(presetOrSnapshot, keys);
}

/**
 * Returns the control IDs that should be visible in the Playground for
 * a given preset & feature combination.
 *
 * Rules:
 *   - Required controls always shown (even if not bound — shown disabled)
 *   - Optional controls shown only if bound
 *   - Mask controls (mask_blur, mask_expand) shown only if bound
 *   - txt2img never shows mask controls unless explicitly bound
 */
export function getVisibleControlsForPreset(presetOrSnapshot, featureId) {
  if (!presetOrSnapshot || !featureId) return [];
  const compat = presetOrSnapshot.compatibleFeatures || [];
  if (!compat.includes(featureId)) return [];

  const bindings = presetOrSnapshot.nodeBindings || {};
  const req = FEATURE_REQUIREMENTS[featureId];
  if (!req) return [];

  const visible = new Set();

  // 1. Required controls (always shown)
  req.requiredBindingKeys.forEach((key) => {
    const def = CONTROL_BINDING_DEFS[key];
    if (def && def.isControl !== false) visible.add(def.key);
  });
  // or-required: show the representative control
  if (req.orRequiredBindingKeys) {
    req.orRequiredBindingKeys.forEach((group) => {
      // Show the first control-ID-like entry
      const key = group[0];
      const def = CONTROL_BINDING_DEFS[key];
      if (def && def.isControl !== false) visible.add(def.key);
    });
  }

  // 2. Optional controls — shown only if actually bound
  req.optionalBindingKeys.forEach((key) => {
    const def = CONTROL_BINDING_DEFS[key];
    if (!def || def.isControl === false) return;
    if (bindings[key] && bindings[key].nodeId) {
      visible.add(def.key);
    }
  });

  // 3. Any other control that happens to be bound (edge-case bindings)
  Object.entries(bindings).forEach(([key, val]) => {
    if (val && val.nodeId) {
      const def = CONTROL_BINDING_DEFS[key];
      if (def && def.isControl !== false) visible.add(def.key);
    }
  });

  return Array.from(visible);
}

/**
 * Which required bindings are MISSING (no valid nodeId) for the given
 * preset+feature.  Handles orRequired groups (at least one of group).
 */
export function getMissingRequiredBindings(presetOrSnapshot, featureId) {
  if (!presetOrSnapshot || !featureId) return [];
  const req = FEATURE_REQUIREMENTS[featureId];
  if (!req) return [];

  const missing = [];

  // Check straight-required keys
  req.requiredBindingKeys.forEach((key) => {
    if (!_isBound(presetOrSnapshot, key)) {
      const def = CONTROL_BINDING_DEFS[key];
      missing.push(def || { key, label: key });
    }
  });

  // Check or-required groups
  if (req.orRequiredBindingKeys) {
    req.orRequiredBindingKeys.forEach((group) => {
      const anyBound = _isAnyBound(presetOrSnapshot, group);
      if (!anyBound) {
        const rep = CONTROL_BINDING_DEFS[group[0]];
        missing.push(
          rep
            ? { ...rep, label: `${rep.label} (or ${group.slice(1).join(", ")})` }
            : { key: group[0], label: group.join(" or ") },
        );
      }
    });
  }

  return missing;
}

/**
 * Full capability summary for a preset+feature combination.
 */
export function getPresetCapabilitySummary(presetOrSnapshot, featureId) {
  if (!presetOrSnapshot || !featureId) {
    return { featureId, status: "unknown", disabledReason: "", allRequiredMet: false, runnable: false };
  }

  const req = FEATURE_REQUIREMENTS[featureId];
  const hasApiGraph = !!(presetOrSnapshot.apiPromptJson || presetOrSnapshot.graphJson);
  const hasOutputBinding = _isBound(presetOrSnapshot, "output");
  const missingRequired = getMissingRequiredBindings(presetOrSnapshot, featureId);
  const allRequiredMet = missingRequired.length === 0;
  const hasApiGraphSupport = req ? req.needsApiGraph : false;
  const apiGraphOk = hasApiGraphSupport ? hasApiGraph : true;

  const requiredDefs = getRequiredBindingsForFeature(featureId);
  const optionalDefs = getOptionalBindingsForFeature(featureId);

  const requiredBindings = requiredDefs.map((d) => ({
    ...d,
    bound: _isBound(presetOrSnapshot, d.key),
    binding: (presetOrSnapshot.nodeBindings || {})[d.key] || null,
  }));

  const optionalBindings = optionalDefs.map((d) => ({
    ...d,
    bound: _isBound(presetOrSnapshot, d.key),
    binding: (presetOrSnapshot.nodeBindings || {})[d.key] || null,
  }));

  return {
    featureId,
    status: presetOrSnapshot.status || "unknown",
    disabledReason: presetOrSnapshot.disabledReason || "",
    hasApiGraph,
    hasOutputBinding,
    apiGraphOk,
    allRequiredMet,
    missingRequired,
    requiredBindings,
    optionalBindings,
    totalRequired: requiredDefs.length,
    totalBoundRequired: requiredBindings.filter((r) => r.bound).length,
    totalOptional: optionalDefs.length,
    totalBoundOptional: optionalBindings.filter((r) => r.bound).length,
    runnable: presetOrSnapshot.status === "runnable" && !presetOrSnapshot.archived,
  };
}

/**
 * Determine which control IDs are eligible as experiment axes given a set
 * of presets (selected for comparison).  An axis is eligible only if ALL
 * selected runnable presets have a binding for it AND support the feature.
 */
export function getAxisEligibilityForPresets(presets, featureId) {
  if (!presets || presets.length === 0 || !featureId) return [];

  const runnablePresets = presets.filter(
    (p) => p.status === "runnable" && !p.archived && (p.compatibleFeatures || []).includes(featureId),
  );
  if (runnablePresets.length === 0) return [];

  const eligible = [];

  for (const [key, def] of Object.entries(CONTROL_BINDING_DEFS)) {
    if (!def.experimentEligible || def.isControl === false) continue;

    const allSupport = runnablePresets.every((p) => {
      const bindings = p.nodeBindings || {};
      return !!(bindings[key] && bindings[key].nodeId);
    });

    if (allSupport) eligible.push(key);
  }

  return eligible;
}

/**
 * Returns a map of { controlId: reasonString } for controls that are not
 * available for the given preset+feature.
 */
export function getUnavailableControlReasons(presetOrSnapshot, featureId) {
  const reasons = {};
  if (!presetOrSnapshot || !featureId) return reasons;

  const compat = presetOrSnapshot.compatibleFeatures || [];
  if (!compat.includes(featureId)) {
    return { _feature: `Preset does not support "${featureId}".` };
  }

  const missingRequired = getMissingRequiredBindings(presetOrSnapshot, featureId);
  missingRequired.forEach((d) => {
    reasons[d.key] = `Requires "${d.label}" binding`;
  });

  // Check API graph
  const req = FEATURE_REQUIREMENTS[featureId];
  if (req && req.needsApiGraph) {
    if (!presetOrSnapshot.apiPromptJson && !presetOrSnapshot.graphJson) {
      reasons._apiGraph = "No API graph captured";
    }
  }

  return reasons;
}
