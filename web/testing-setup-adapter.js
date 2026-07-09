// web/testing-setup-adapter.js
//
// Frontend-only normalized draft adapter for the Setup UI.
//
// Owns UI normalization (default draft creation, safe merge), runtime
// preview state helpers (never persisted), and backend payload serialization
// (wraps user-intent drafts into normalized_draft payloads for the compile
// and create endpoints).
//
// The persisted draft is user intent only. Preview/error/loading state must
// stay separate — use createPreviewState() for ephemeral runtime views.
//
// Schema: generation_type ("t2i" | "img2img"), variable_modes with per-variable
// mode selection ("default" | "testing" | "controlled"), workflow-local
// multiple stacks with per-stack lora_selections and lora_scope.

export const adapterVersion = "0.2.0";

const VARIABLE_NAMES = [
  "prompt",
  "negative_prompt",
  "input_image",
  "model_stack",
  "lora_config",
  "seed",
  "sampler",
  "scheduler",
  "steps",
  "guidance",
  "denoise",
  "resolution",
];

function createDefaultVariableModes() {
  const modes = {};
  VARIABLE_NAMES.forEach((name) => {
    let mode = "default";
    // Prompt, seed, sampler, steps start as testing by default
    if (["prompt", "seed", "sampler", "steps", "model_stack"].includes(name)) {
      mode = "testing";
    }
    // input_image is disabled by default (only relevant for img2img)
    const enabled = name !== "input_image";
    modes[name] = { mode, enabled };
  });
  return modes;
}

// ── Default draft creation ──────────────────────────────────────────────

export function createDefaultDraft() {
  return {
    name: "Untitled experiment",
    notes: "",
    generation_type: "t2i",
    variable_modes: createDefaultVariableModes(),
    workflows: [],
    prompts: { items: [] },
    images: { mode: "cartesian", items: [] },
    prompt_image_pairing: "cartesian",
    loras: {
      selections: [{ id: "L_no", label: "No LoRA", loras: [], enabled: true }],
    },
    axes: {
      shared: { seed: { mode: "list", values: [1, 2, 3] } },
      per_workflow: {},
    },
    tested_values: {},
    controlled_values: {},
    compatibility_mode: "standard",
    advanced_execution: { execution_mode: "sequential", max_parallel: 1 },
    container_mode: "single",
    max_containers: 1,
  };
}

// ── UI normalization ────────────────────────────────────────────────────

export function normalizeDraft(draft) {
  if (!draft || typeof draft !== "object") return createDefaultDraft();
  const def = createDefaultDraft();
  return {
    name: draft.name || def.name,
    notes: draft.notes || def.notes,
    generation_type: ["t2i", "img2img"].includes(draft.generation_type)
      ? draft.generation_type
      : def.generation_type,
    variable_modes: {
      ...def.variable_modes,
      ...(draft.variable_modes || {}),
    },
    workflows: Array.isArray(draft.workflows)
      ? draft.workflows.map((wf) => normalizeWorkflow(wf))
      : [],
    prompts: draft.prompts || def.prompts,
    images: draft.images || def.images,
    prompt_image_pairing: draft.prompt_image_pairing || def.prompt_image_pairing,
    loras: draft.loras || def.loras,
    axes: {
      ...def.axes,
      ...(draft.axes || {}),
    },
    tested_values: draft.tested_values || {},
    controlled_values: draft.controlled_values || {},
    compatibility_mode: draft.compatibility_mode || def.compatibility_mode,
    advanced_execution: {
      ...def.advanced_execution,
      ...(draft.advanced_execution || {}),
    },
    container_mode:
      typeof draft.container_mode === "string"
        ? draft.container_mode
        : def.container_mode,
    max_containers:
      typeof draft.max_containers === "number"
        ? draft.max_containers
        : def.max_containers,
  };
}

function normalizeWorkflow(wf) {
  if (!wf || typeof wf !== "object") return {};
  return {
    profile_id: wf.profile_id || "",
    stacks: Array.isArray(wf.stacks)
      ? wf.stacks.map((stack) => normalizeStack(stack))
      : [],
    loader_target_group_id:
      wf.loader_target_group_id || "g_default",
    main_triple: wf.main_triple || { id: "main" },
    selected_triple_ids: wf.selected_triple_ids || ["main"],
    subprofile_triples: wf.subprofile_triples || [],
    lora_slots: wf.lora_slots || [],
  };
}

function normalizeStack(stack) {
  if (!stack || typeof stack !== "object") return {};
  return {
    stack_id: stack.stack_id || "s1",
    loader_target_group_id:
      stack.loader_target_group_id || "g_default",
    main_triple: stack.main_triple || { id: "main" },
    selected_triple_ids: stack.selected_triple_ids || ["main"],
    subprofile_triples: stack.subprofile_triples || [],
    lora_selections: stack.lora_selections || [],
    lora_scope: ["all", "selected", "matrix"].includes(stack.lora_scope)
      ? stack.lora_scope
      : "all",
    lora_scope_stacks: Array.isArray(stack.lora_scope_stacks)
      ? stack.lora_scope_stacks
      : [],
  };
}

// ── Safe merge ──────────────────────────────────────────────────────────

export function mergeDraft(prev, next) {
  if (!prev && !next) return createDefaultDraft();
  if (!prev) return normalizeDraft(next);
  if (!next) return normalizeDraft(prev);
  const base = normalizeDraft(prev);
  const override = normalizeDraft(next);
  return {
    ...base,
    ...override,
    // Deep merge for nested structures
    variable_modes: { ...base.variable_modes, ...override.variable_modes },
    workflows: override.workflows.length > 0 ? override.workflows : base.workflows,
    loras: override.loras || base.loras,
    axes: { ...base.axes, ...override.axes },
    prompts: override.prompts || base.prompts,
    images: override.images || base.images,
    tested_values: { ...base.tested_values, ...override.tested_values },
    controlled_values: { ...base.controlled_values, ...override.controlled_values },
    advanced_execution: { ...base.advanced_execution, ...override.advanced_execution },
  };
}

// ── Variable mode helpers ───────────────────────────────────────────────

export function getActiveTestingVariables(variableModes) {
  const modes = variableModes || createDefaultVariableModes();
  return Object.entries(modes)
    .filter(([, v]) => v.enabled !== false && v.mode === "testing")
    .map(([key]) => key);
}

export function getActiveControlledVariables(variableModes) {
  const modes = variableModes || createDefaultVariableModes();
  return Object.entries(modes)
    .filter(([, v]) => v.enabled !== false && v.mode === "controlled")
    .map(([key]) => key);
}

export function isVariableMode(variableModes, variableName, mode) {
  const v = (variableModes || {})[variableName];
  return v && v.mode === mode;
}

export function cycleVariableMode(variableModes, variableName) {
  const current = ((variableModes || {})[variableName] || {}).mode || "default";
  const next = current === "default" ? "testing" : current === "testing" ? "controlled" : "default";
  return {
    ...(variableModes || {}),
    [variableName]: {
      ...((variableModes || {})[variableName] || { enabled: true }),
      mode: next,
    },
  };
}

export function getVariableLabel(name) {
  const labels = {
    prompt: "Prompt",
    negative_prompt: "Negative Prompt",
    input_image: "Input Image",
    model_stack: "Model Stack",
    lora_config: "LoRA Config",
    seed: "Seed",
    sampler: "Sampler",
    scheduler: "Scheduler",
    steps: "Steps",
    guidance: "Guidance (CFG)",
    denoise: "Denoise",
    resolution: "Resolution",
  };
  return labels[name] || name;
}

// ── Backend payload serialization ───────────────────────────────────────
//
// These functions convert a user-intent draft into the normalized_draft
// format the backend compile/create routes accept.

/**
 * Build the normalized_draft object the backend expects.
 * The frontend draft uses a flat structure (name, notes, loras.selections);
 * this function re-shapes it into the backend-authoritative normalized
 * schema (experiment_id, revision, per-workflow stacks with lora_selections,
 * generation_type, variable_modes, tested_values, controlled_values, etc.).
 */
function toBackendDraft(draft) {
  const name = draft.name || "Untitled experiment";
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40);
  const expId = `${slug}-${Date.now().toString(36)}`;

  const topLevelLoras = (draft.loras && draft.loras.selections) || [];

  const workflows = (draft.workflows || []).map((wf) => ({
    profile_id: wf.profile_id || "",
    stacks:
      wf.stacks && wf.stacks.length > 0
        ? wf.stacks.map((stack) => ({
            stack_id: stack.stack_id || "s1",
            loader_target_group_id:
              stack.loader_target_group_id || "g_default",
            main_triple: stack.main_triple || { id: "main" },
            selected_triple_ids: stack.selected_triple_ids || ["main"],
            subprofile_triples: stack.subprofile_triples || [],
            lora_selections:
              Array.isArray(stack.lora_selections) && stack.lora_selections.length > 0
                ? stack.lora_selections
                : topLevelLoras,
            lora_scope: stack.lora_scope || "all",
            lora_scope_stacks: stack.lora_scope_stacks || [],
          }))
        : [
            {
              stack_id: "s1",
              loader_target_group_id:
                wf.loader_target_group_id || "g_default",
              main_triple: wf.main_triple || { id: "main" },
              selected_triple_ids: wf.selected_triple_ids || ["main"],
              subprofile_triples: wf.subprofile_triples || [],
              lora_selections: topLevelLoras,
              lora_scope: "all",
              lora_scope_stacks: [],
            },
          ],
    lora_slots: wf.lora_slots || [],
  }));

  return {
    experiment_id: expId,
    revision: 1,
    name,
    notes: draft.notes || "",
    generation_type: draft.generation_type || "t2i",
    profile_type: draft.generation_type || "t2i",
    prompt_image_pairing: draft.prompt_image_pairing || "cartesian",
    variable_modes: draft.variable_modes || {},
    tested_values: draft.tested_values || {},
    controlled_values: draft.controlled_values || {},
    compatibility_mode: draft.compatibility_mode || "standard",
    advanced_execution: draft.advanced_execution || {
      execution_mode: "sequential",
      max_parallel: 1,
    },
    workflows,
    prompts: draft.prompts || { items: [] },
    images: draft.images || { mode: "cartesian", items: [] },
    axes: draft.axes || { shared: {}, per_workflow: {} },
    container_mode: draft.container_mode || "single",
    max_containers:
      typeof draft.max_containers === "number"
        ? draft.max_containers
        : 1,
  };
}

/**
 * Wrap a draft into a compile payload ({ normalized_draft: ... }).
 * Used by the Preview section's Compile button.
 */
export function draftToCompilePayload(draft) {
  const backend = toBackendDraft(normalizeDraft(draft));
  return { normalized_draft: backend };
}

/**
 * Wrap a draft into a create payload ({ normalized_draft: ..., max_containers }).
 * Used by the Run flow.
 */
export function draftToCreatePayload(draft) {
  const normalized = normalizeDraft(draft);
  const backend = toBackendDraft(normalized);
  return {
    normalized_draft: backend,
    max_containers: normalized.max_containers || 1,
  };
}

/**
 * Build a minimal start payload for the run flow.
 * The backend can look up the stored compilation from the create event,
 * so we only need max_containers.
 */
export function draftToStartPayload(draft) {
  return {
    max_containers:
      typeof draft.max_containers === "number"
        ? draft.max_containers
        : 1,
  };
}

// ── Stack helpers ───────────────────────────────────────────────────────

/**
 * Add a new default stack to a workflow.
 */
export function addStackToWorkflow(wf) {
  const stacks = wf.stacks || [];
  const nextId = `s${stacks.length + 1}`;
  return {
    ...wf,
    stacks: [
      ...stacks,
      {
        stack_id: nextId,
        loader_target_group_id: "g_default",
        main_triple: { id: "main" },
        selected_triple_ids: ["main"],
        subprofile_triples: [],
        lora_selections: [],
        lora_scope: "all",
        lora_scope_stacks: [],
      },
    ],
  };
}

/**
 * Remove a stack from a workflow by stack_id.
 */
export function removeStackFromWorkflow(wf, stackId) {
  const stacks = (wf.stacks || []).filter((s) => s.stack_id !== stackId);
  return { ...wf, stacks };
}

/**
 * Update a stack in a workflow by stack_id.
 */
export function updateStackInWorkflow(wf, stackId, updates) {
  const stacks = (wf.stacks || []).map((s) =>
    s.stack_id === stackId ? { ...s, ...updates } : s
  );
  return { ...wf, stacks };
}

/**
 * Duplicate a stack in a workflow.
 */
export function duplicateStackInWorkflow(wf, stackId) {
  const source = (wf.stacks || []).find((s) => s.stack_id === stackId);
  if (!source) return wf;
  const stacks = wf.stacks || [];
  const nextId = `s${stacks.length + 1}`;
  return {
    ...wf,
    stacks: [
      ...stacks,
      { ...source, stack_id: nextId },
    ],
  };
}

// ── LoRA scope helpers ──────────────────────────────────────────────────

export function cycleLoraScope(currentScope) {
  const scopes = ["all", "selected", "matrix"];
  const idx = scopes.indexOf(currentScope);
  return scopes[(idx + 1) % scopes.length];
}

export function getLoraScopeLabel(scope) {
  const labels = {
    all: "All Selected Stacks",
    selected: "Selected Stacks",
    matrix: "Per-Stack Matrix",
  };
  return labels[scope] || scope;
}

// ── Runtime preview state (NOT persisted) ───────────────────────────────
//
// Returns an ephemeral stats object derived from the current draft.
// This is intentionally kept separate from the draft itself.

export function createPreviewState(draft) {
  const normalized = normalizeDraft(draft);
  const wf = normalized.workflows || [];
  const prompts = normalized.prompts || { items: [] };
  const loraSel = (normalized.loras || {}).selections || [];
  const seedAxis = ((normalized.axes || {}).shared || {}).seed || {};
  const varModes = normalized.variable_modes || {};

  const testingVars = getActiveTestingVariables(varModes);
  const controlledVars = getActiveControlledVariables(varModes);

  // Count total stacks across all workflows
  let totalStacks = 0;
  wf.forEach((workflow) => {
    totalStacks += (workflow.stacks || []).length;
  });

  return {
    // Incrementing counter so consumers can detect changes
    _revision: Date.now(),
    // Generation type
    generationType: normalized.generation_type || "t2i",
    // Workflow stats
    workflowCount: wf.length,
    hasWorkflows: wf.length > 0,
    totalStacks,
    // Prompt stats
    promptCount: prompts.items.length,
    // LoRA stats
    activeLoraCount: loraSel.filter(
      (s) => s.enabled !== false && s.loras && s.loras.length > 0
    ).length,
    // Variable mode stats
    testingVariableCount: testingVars.length,
    controlledVariableCount: controlledVars.length,
    // Axis stats
    seedCount: Array.isArray(seedAxis.values) ? seedAxis.values.length : 0,
    // Summary
    hasContent: wf.length > 0 && prompts.items.length > 0,
  };
}

export { VARIABLE_NAMES, createDefaultVariableModes };
