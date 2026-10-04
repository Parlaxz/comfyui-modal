// Modal Studio — Workflow Run Frontend Logic
//
// Frontend logic + state for the Studio Workflow → Playground flow:
// loading the workflow library, resolving run-context bundles, deriving
// control defaults, validating mapped controls, resolving runnable gating,
// and building run payloads.
//
// Node-testable: no DOM or browser globals at module top level. All
// localStorage access lives in studio-playground-state.js (guarded there)
// and is re-exported from here for convenience.
//
// The store is a plain object (createWorkflowRunStore) mutated through its
// setter methods; every other export is a pure function over that store.

import {
  listWorkflows,
  listWorkflowVersions,
  getWorkflowRunContext,
  listVersionPresets,
  getWorkflowPreset,
} from "./studio-backend-api.js";

import {
  saveWorkflowSelection,
  loadWorkflowSelection,
  clearWorkflowSelection,
  saveWorkflowHandoff,
  takeWorkflowHandoff,
} from "./studio-playground-state.js";

// Re-export persistence so consumers only need this one module.
export {
  saveWorkflowSelection,
  loadWorkflowSelection,
  clearWorkflowSelection,
  saveWorkflowHandoff,
  takeWorkflowHandoff,
};

// localStorage keys owned by studio-playground-state.js (kept in sync).
export const PERSISTENCE_KEYS = {
  workflowSelection: "comfymodal.studio.playground.workflow.v1",
  workflowHandoff: "comfymodal.studio.playground.workflow-handoff.v1",
};

const FEATURE_ID = "txt2img";

// ── Store ────────────────────────────────────────────────────────────────

/**
 * Create a fresh workflow-run store.
 * @returns {object} Plain mutable state + setter methods.
 */
export function createWorkflowRunStore() {
  return {
    workflowId: "",
    workflowVersionId: "",
    presetId: "",
    workflowName: "",
    presetName: "",
    library: [],
    versions: [],
    presets: [],
    runContext: null,
    controlValues: {},
    status: "idle",
    error: "",
    reasons: [],
    handoff: null,
    lastLoadedAt: 0,

    setWorkflowId(id) { this.workflowId = id != null ? String(id) : ""; },
    setVersionId(id) { this.workflowVersionId = id != null ? String(id) : ""; },
    setPresetId(id) { this.presetId = id != null ? String(id) : ""; },
    setWorkflowName(name) { this.workflowName = name != null ? String(name) : ""; },
    setPresetName(name) { this.presetName = name != null ? String(name) : ""; },
    setControlValue(role, value) { this.controlValues[role] = value; },
    setControlValues(dict) {
      this.controlValues = dict && typeof dict === "object" ? { ...dict } : {};
    },
    setRunContext(ctx) { this.runContext = ctx || null; },
    setLibrary(arr) { this.library = Array.isArray(arr) ? arr.slice() : []; },
    setVersions(arr) { this.versions = Array.isArray(arr) ? arr.slice() : []; },
    setPresets(arr) { this.presets = Array.isArray(arr) ? arr.slice() : []; },
    setStatus(s) { this.status = s || "idle"; },
    setError(e) { this.error = e != null ? String(e) : ""; },
    setReasons(arr) { this.reasons = Array.isArray(arr) ? arr.map(String) : []; },
    setHandoff(h) { this.handoff = h && typeof h === "object" ? { ...h } : null; },

    reset() {
      this.workflowId = "";
      this.workflowVersionId = "";
      this.presetId = "";
      this.workflowName = "";
      this.presetName = "";
      this.library = [];
      this.versions = [];
      this.presets = [];
      this.runContext = null;
      this.controlValues = {};
      this.status = "idle";
      this.error = "";
      this.reasons = [];
      this.handoff = null;
      this.lastLoadedAt = 0;
    },
  };
}

// ── Small helpers ─────────────────────────────────────────────────────────

function _errorMessage(err, fallback) {
  if (err == null) return fallback;
  if (typeof err === "string") return err;
  if (err.message) return String(err.message);
  try { return JSON.stringify(err); } catch (e) { return fallback; }
}

/** Union of a preset's values + model_choices (model_choices override values). */
function _presetRoleValues(preset) {
  if (!preset || typeof preset !== "object") return {};
  const values = preset.values && typeof preset.values === "object" ? preset.values : {};
  const choices = preset.model_choices && typeof preset.model_choices === "object" ? preset.model_choices : {};
  return { ...values, ...choices };
}

/**
 * Resolve the default preset for a version: the workflow default preset id
 * only when it belongs to this version's preset list, otherwise the first
 * preset, otherwise null.
 */
function _resolveDefaultPreset(presets, defaultPresetId) {
  if (!Array.isArray(presets) || !presets.length) return null;
  if (defaultPresetId) {
    const match = presets.find((p) => String(p.preset_id) === String(defaultPresetId));
    if (match) return match;
  }
  return presets[0];
}

/** Pick the version to select: latest_version_id when present, else newest version_number. */
function _pickDefaultVersionId(versions, latestVersionId) {
  if (!Array.isArray(versions) || !versions.length) return "";
  if (latestVersionId) {
    const match = versions.find((v) => String(v.workflow_version_id) === String(latestVersionId));
    if (match) return String(match.workflow_version_id);
  }
  const sorted = versions
    .filter((v) => v && v.workflow_version_id)
    .slice()
    .sort((a, b) => (Number(b.version_number) || 0) - (Number(a.version_number) || 0));
  return sorted.length ? String(sorted[0].workflow_version_id) : "";
}

/**
 * Reasons that gate runnability, passed through verbatim from the backend
 * version state plus local completeness (mapping + preset selection).
 */
function _gateReasons(store) {
  const ctx = store.runContext;
  const reasons = [];
  if (!ctx || !ctx.version) {
    reasons.push("no run context");
    return reasons;
  }
  const state = ctx.version.state || {};
  if (state.runnable !== true && Array.isArray(state.reasons)) {
    reasons.push(...state.reasons.map(String));
  }
  if (!ctx.mapping) reasons.push("missing mapping");
  if (!store.presetId) reasons.push("no preset selected for version");
  return reasons;
}

/** Entry default when neither preset nor the graph define a value. */
function _entryDefault(entry) {
  if (Array.isArray(entry.enum_options) && entry.enum_options.length) {
    return entry.required ? entry.enum_options[0] : undefined;
  }
  if (entry.control_kind === "boolean") return false;
  if (entry.minimum != null) return entry.minimum;
  return undefined;
}

// ── Library / selection loading ───────────────────────────────────────────

/**
 * Load the workflow library into the store. Never throws.
 * @param {string} apiBase
 * @param {object} store
 * @returns {Promise<Array>}
 */
export async function loadWorkflowLibrary(apiBase, store) {
  try {
    const data = await listWorkflows(apiBase);
    if (!data || data.status === "error") {
      const msg = (data && (data.message || data.error)) || "failed to load workflow library";
      store.setError(msg);
      store.setLibrary([]);
      return [];
    }
    const items = Array.isArray(data.workflows) ? data.workflows : [];
    store.setLibrary(items);
    return items;
  } catch (err) {
    store.setError(_errorMessage(err, "failed to load workflow library"));
    store.setLibrary([]);
    return [];
  }
}

/**
 * Fetch + cache the run-context bundle for a workflow/version.
 * Stores the whole bundle so Run does not refetch.
 * @param {string} apiBase
 * @param {object} store
 * @param {string} workflowId
 * @param {string} versionId
 * @returns {Promise<{ok: boolean, error?: string, reasons?: string[]}>}
 */
export async function loadRunContext(apiBase, store, workflowId, versionId) {
  try {
    const data = await getWorkflowRunContext(apiBase, workflowId, versionId);
    if (!data || data.status !== "ok") {
      const msg = (data && (data.message || data.error)) || "failed to load run context";
      store.setStatus("error");
      store.setError(msg);
      store.setReasons([msg]);
      return { ok: false, error: msg, reasons: [msg] };
    }
    const version = data.version;
    if (!version || !version.state) {
      const msg = "run context missing version state";
      store.setStatus("error");
      store.setError(msg);
      store.setReasons([msg]);
      return { ok: false, error: msg, reasons: [msg] };
    }
    store.setRunContext(data);
    if (version.workflow_version_id != null) store.setVersionId(String(version.workflow_version_id));
    if (data.workflow && data.workflow.name != null) store.setWorkflowName(String(data.workflow.name));

    const reasons = [];
    if (version.state.runnable !== true && Array.isArray(version.state.reasons)) {
      reasons.push(...version.state.reasons.map(String));
    }
    if (!data.mapping) reasons.push("missing mapping");
    store.setReasons(reasons);
    store.lastLoadedAt = Date.now();
    return { ok: true, reasons };
  } catch (err) {
    const msg = _errorMessage(err, "failed to load run context");
    store.setStatus("error");
    store.setError(msg);
    store.setReasons([msg]);
    return { ok: false, error: msg, reasons: [msg] };
  }
}

/**
 * Select a workflow: reset version/preset, load versions + run-context +
 * presets, resolve the default preset.
 * @param {string} apiBase
 * @param {object} store
 * @param {string} workflowId
 * @returns {Promise<{ok: boolean, error?: string, reasons?: string[]}>}
 */
export async function selectWorkflow(apiBase, store, workflowId) {
  store.setStatus("loading");
  store.setError("");
  try {
    if (!workflowId) {
      store.setStatus("error");
      store.setError("no workflow selected");
      store.setReasons(["no workflow selected"]);
      return { ok: false, error: "no workflow selected", reasons: ["no workflow selected"] };
    }
    // Reset version/preset state from any previous selection.
    store.setVersionId("");
    store.setPresetId("");
    store.setPresetName("");
    store.setRunContext(null);
    store.controlValues = {};
    store.setWorkflowId(workflowId);

    const versionsData = await listWorkflowVersions(apiBase, workflowId);
    const versions = (versionsData && Array.isArray(versionsData.versions)) ? versionsData.versions : [];
    store.setVersions(versions);

    if (!versions.length) {
      store.setStatus("error");
      store.setError("workflow has no versions");
      store.setReasons(["no versions"]);
      return { ok: false, error: "workflow has no versions", reasons: ["no versions"] };
    }

    const wf = (store.library || []).find((w) => String(w.workflow_id) === String(workflowId));
    const versionId = _pickDefaultVersionId(versions, wf && wf.latest_version_id);
    if (!versionId) {
      store.setStatus("error");
      store.setError("workflow has no runnable version");
      store.setReasons(["no versions"]);
      return { ok: false, error: "workflow has no runnable version", reasons: ["no versions"] };
    }

    const ctxResult = await loadRunContext(apiBase, store, workflowId, versionId);
    if (!ctxResult.ok) {
      store.setStatus("error");
      return { ok: false, error: ctxResult.error, reasons: ctxResult.reasons };
    }

    const presetsData = await listVersionPresets(apiBase, versionId);
    const presets = (presetsData && Array.isArray(presetsData.presets)) ? presetsData.presets : [];
    store.setPresets(presets);

    const defaultPresetId = store.runContext && store.runContext.workflow
      ? store.runContext.workflow.default_preset_id : "";
    const preset = _resolveDefaultPreset(presets, defaultPresetId);
    if (preset) {
      store.setPresetId(String(preset.preset_id));
      store.setPresetName(preset.name || "");
    } else {
      store.setPresetId("");
      store.setPresetName("");
      store.setReasons([..._gateReasons(store).filter((r) => r !== "no preset selected for version"), "no preset"]);
    }
    store.controlValues = defaultValuesFromContext(store, preset || null);
    store.lastLoadedAt = Date.now();
    store.setStatus("ready");
    return { ok: true };
  } catch (err) {
    const msg = _errorMessage(err, "failed to select workflow");
    store.setStatus("error");
    store.setError(msg);
    store.setReasons([msg]);
    return { ok: false, error: msg, reasons: [msg] };
  }
}

/**
 * Select a version of the current workflow: reload run-context + presets
 * and reset control values to the version's defaults.
 * @param {string} apiBase
 * @param {object} store
 * @param {string} versionId
 * @returns {Promise<{ok: boolean, error?: string, reasons?: string[]}>}
 */
export async function selectVersion(apiBase, store, versionId) {
  store.setStatus("loading");
  store.setError("");
  try {
    if (!versionId) {
      store.setStatus("error");
      store.setError("no version selected");
      store.setReasons(["no version selected"]);
      return { ok: false, error: "no version selected", reasons: ["no version selected"] };
    }
    store.setPresetId("");
    store.setPresetName("");
    store.controlValues = {};

    const ctxResult = await loadRunContext(apiBase, store, store.workflowId, versionId);
    if (!ctxResult.ok) {
      store.setStatus("error");
      return { ok: false, error: ctxResult.error, reasons: ctxResult.reasons };
    }

    const presetsData = await listVersionPresets(apiBase, versionId);
    const presets = (presetsData && Array.isArray(presetsData.presets)) ? presetsData.presets : [];
    store.setPresets(presets);

    // Default preset for THIS version: workflow default only when it belongs
    // to this version's presets; else first preset; else none.
    const defaultPresetId = store.runContext && store.runContext.workflow
      ? store.runContext.workflow.default_preset_id : "";
    const preset = _resolveDefaultPreset(presets, defaultPresetId);
    if (preset) {
      store.setPresetId(String(preset.preset_id));
      store.setPresetName(preset.name || "");
    } else {
      store.setPresetId("");
      store.setPresetName("");
      store.setReasons([..._gateReasons(store).filter((r) => r !== "no preset selected for version"), "no preset for version"]);
    }
    store.controlValues = defaultValuesFromContext(store, preset || null);
    store.lastLoadedAt = Date.now();
    store.setStatus("ready");
    return { ok: true };
  } catch (err) {
    const msg = _errorMessage(err, "failed to select version");
    store.setStatus("error");
    store.setError(msg);
    store.setReasons([msg]);
    return { ok: false, error: msg, reasons: [msg] };
  }
}

/**
 * Select a preset for the current version. Verifies the preset belongs to
 * the selected version; never silently substitutes.
 * @param {string} apiBase
 * @param {object} store
 * @param {string} presetId
 * @returns {Promise<{ok: boolean, error?: string, reasons?: string[]}>}
 */
export async function selectPreset(apiBase, store, presetId) {
  store.setStatus("loading");
  store.setError("");
  try {
    if (!presetId) {
      store.setPresetId("");
      store.setPresetName("");
      store.controlValues = defaultValuesFromContext(store, null);
      store.setReasons(_gateReasons(store));
      store.setStatus("ready");
      return { ok: true };
    }

    const data = await getWorkflowPreset(apiBase, presetId);
    const preset = data && data.status !== "error" && data.preset ? data.preset : null;
    if (!preset || preset.preset_id == null) {
      const msg = (data && (data.message || data.error)) || "preset not found";
      store.setStatus("error");
      store.setError(msg);
      store.setReasons([msg]);
      return { ok: false, error: msg, reasons: [msg] };
    }

    const presetVersionId = preset.workflow_version_id != null ? String(preset.workflow_version_id) : "";
    if (presetVersionId !== String(store.workflowVersionId || "")) {
      const msg = "preset belongs to a different version";
      store.setStatus("error");
      store.setError(msg);
      store.setReasons([msg]);
      return { ok: false, error: msg, reasons: [msg] };
    }

    store.setPresetId(String(preset.preset_id));
    store.setPresetName(preset.name || "");

    // Re-derive control values: preset wins for the roles it defines;
    // other roles keep current controlValues, falling back to graph defaults.
    const schema = getControlSchema(store);
    const fromPreset = _presetRoleValues(preset);
    const current = store.controlValues && typeof store.controlValues === "object" ? store.controlValues : {};
    const graphDefaults = defaultValuesFromContext(store, null);
    const merged = {};
    for (const role of Object.keys(schema)) {
      let value;
      if (Object.prototype.hasOwnProperty.call(fromPreset, role)) {
        value = fromPreset[role];
      } else if (Object.prototype.hasOwnProperty.call(current, role)) {
        value = current[role];
      } else if (Object.prototype.hasOwnProperty.call(graphDefaults, role)) {
        value = graphDefaults[role];
      }
      if (value !== undefined) merged[role] = value;
    }
    store.controlValues = merged;
    store.setReasons(_gateReasons(store));
    store.lastLoadedAt = Date.now();
    store.setStatus("ready");
    return { ok: true };
  } catch (err) {
    const msg = _errorMessage(err, "failed to select preset");
    store.setStatus("error");
    store.setError(msg);
    store.setReasons([msg]);
    return { ok: false, error: msg, reasons: [msg] };
  }
}

// ── Schema / defaults ─────────────────────────────────────────────────────

/**
 * The control schema (semantic_role → mapping entry) from the cached
 * run-context bundle.
 * @param {object} store
 * @returns {object}
 */
export function getControlSchema(store) {
  const ctx = store && store.runContext;
  return ctx && ctx.control_schema && typeof ctx.control_schema === "object" ? ctx.control_schema : {};
}

/**
 * Derive default control values for every schema entry. Precedence:
 * preset.values → preset.model_choices → graph current value (verbatim,
 * including 0 / 0.0 / false / "") → entry default. Values that cannot be
 * resolved are left unset (backend decides). Never invents values outside
 * graph-declared options.
 * @param {object} store
 * @param {object|null} [preset]
 * @returns {object} { role: value }
 */
export function defaultValuesFromContext(store, preset) {
  const schema = getControlSchema(store);
  const presetRoles = _presetRoleValues(preset);
  const executable = store && store.runContext && store.runContext.version
    ? store.runContext.version.executable_prompt
    : null;
  const values = {};
  for (const [role, entry] of Object.entries(schema)) {
    if (!entry || typeof entry !== "object") continue;
    let value;
    if (Object.prototype.hasOwnProperty.call(presetRoles, role)) {
      value = presetRoles[role];
    } else if (executable) {
      const node = executable[String(entry.node_id)];
      if (node && node.inputs && Object.prototype.hasOwnProperty.call(node.inputs, entry.input_name)) {
        value = node.inputs[entry.input_name];
      }
    }
    if (value === undefined) value = _entryDefault(entry);
    if (value !== undefined) values[role] = value;
  }
  return values;
}

// ── Validation ────────────────────────────────────────────────────────────

/**
 * Validate mapped control values against the control schema. No coercion:
 * 0, 0.0, false and "" are preserved verbatim. Returns only schema-known
 * keys plus errors for unknown keys / rule violations / missing required.
 * @param {object} values
 * @param {object} controlSchema
 * @returns {{values: object, errors: Array<{field: string, message: string}>}}
 */
export function validateMappedValues(values, controlSchema) {
  const schema = controlSchema && typeof controlSchema === "object" ? controlSchema : {};
  const src = values && typeof values === "object" ? values : {};
  const cleaned = {};
  const errors = [];

  for (const [key, value] of Object.entries(src)) {
    const entry = schema[key];
    if (!entry) {
      errors.push({ field: key, message: `unknown control '${key}'` });
      continue;
    }
    const present = value !== undefined && value !== null;
    if (Array.isArray(entry.enum_options) && entry.enum_options.length && present) {
      if (!entry.enum_options.some((opt) => opt === value)) {
        errors.push({ field: key, message: `must be one of: ${entry.enum_options.join(", ")}` });
      }
    }
    if (present && typeof value === "number") {
      if (typeof entry.minimum === "number" && value < entry.minimum) {
        errors.push({ field: key, message: `must be >= ${entry.minimum}` });
      }
      if (typeof entry.maximum === "number" && value > entry.maximum) {
        errors.push({ field: key, message: `must be <= ${entry.maximum}` });
      }
    }
    if (entry.required && (value === undefined || value === null ||
        (typeof value === "string" && value.trim() === ""))) {
      errors.push({ field: key, message: "required" });
    }
    cleaned[key] = value;
  }

  // Completeness: every schema-required role must be present.
  for (const [key, entry] of Object.entries(schema)) {
    if (entry && entry.required && !Object.prototype.hasOwnProperty.call(src, key)) {
      errors.push({ field: key, message: `missing required control '${key}'` });
    }
  }

  return { values: cleaned, errors };
}

/**
 * Merge a preset's values/model_choices with caller overrides and validate
 * the result.
 * @param {object|null} preset
 * @param {object} overrides
 * @param {object} controlSchema
 * @returns {{values: object, errors: Array<{field: string, message: string}>}}
 */
export function mergePresetAndOverrides(preset, overrides, controlSchema) {
  const base = preset
    ? {
        ...((preset.values && typeof preset.values === "object") ? preset.values : {}),
        ...((preset.model_choices && typeof preset.model_choices === "object") ? preset.model_choices : {}),
      }
    : {};
  const merged = { ...base, ...(overrides && typeof overrides === "object" ? overrides : {}) };
  return validateMappedValues(merged, controlSchema);
}

/**
 * Runnable gating: backend state reasons (verbatim) + mapping/preset/control
 * completeness. Run must be disabled unless runnable.
 * @param {object} store
 * @returns {{runnable: boolean, reasons: string[]}}
 */
export function resolveRunnable(store) {
  if (store.status === "error") {
    return { runnable: false, reasons: [store.error || "load error"] };
  }
  const ctx = store.runContext;
  if (!ctx || !ctx.version) {
    return { runnable: false, reasons: ["no run context"] };
  }
  const reasons = [];
  let runnable = true;
  const state = ctx.version.state || {};
  if (state.runnable === false) {
    runnable = false;
    if (Array.isArray(state.reasons)) reasons.push(...state.reasons.map(String));
  }
  if (!ctx.mapping) {
    runnable = false;
    reasons.push("missing mapping");
  }
  if (!store.presetId) {
    runnable = false;
    reasons.push("no preset selected for version");
  }
  const schema = getControlSchema(store);
  const { errors } = validateMappedValues(store.controlValues || {}, schema);
  if (errors.length) {
    runnable = false;
    reasons.push(errors[0].message);
  }
  return { runnable, reasons };
}

/**
 * Apply the execution target gate after local workflow validation. A remote
 * Golden target does not use the host's model/custom-node inventory; the
 * deployed container remains responsible for rejecting invalid structure.
 */
export function resolveExecutionRunnable(gated, remoteSelected) {
  if (gated.runnable || !remoteSelected) return gated;
  return { runnable: true, reasons: [] };
}

// ── Run payload ───────────────────────────────────────────────────────────

/**
 * Build the run payload. Controls contain ONLY schema-known roles. Callers
 * must run validation first (resolveRunnable / mergePresetAndOverrides);
 * this sanitizes defensively.
 * @param {string} apiBase - API base URL (not embedded in the payload).
 * @param {object} store
 * @param {object} modalOptions
 * @param {object} trace
 * @returns {object}
 */
export function buildRunPayload(apiBase, store, modalOptions, trace) {
  const schema = getControlSchema(store);
  const { values } = validateMappedValues(store.controlValues || {}, schema);
  const version = store.runContext && store.runContext.version;
  return {
    workflow_id: store.workflowId,
    workflow_version_id: store.workflowVersionId,
    preset_id: store.presetId,
    featureId: FEATURE_ID,
    controls: values,
    modal_options: modalOptions && typeof modalOptions === "object" ? { ...modalOptions } : {},
    metadata: {
      source: "studio_playground",
      workflow_id: store.workflowId,
      workflow_version_id: store.workflowVersionId,
      preset_id: store.presetId,
      workflow_name: store.workflowName || "",
      preset_name: store.presetName || "",
      workflow_hash: (version && version.graph_hash) || null,
    },
    trace: trace && typeof trace === "object" ? trace : {},
  };
}

// ── Model compatibility ───────────────────────────────────────────────────

/**
 * Classify model compatibility for the selected workflow/version.
 * Compatible filenames come from workflow/version.compatible_models; a
 * model-role enum option missing from that list is known-incompatible and
 * must never execute.
 * @param {object} store
 * @param {Array<object>} modelLibraryRecords - Model library records with
 *   filename / folder / installed / state fields.
 * @returns {{byFilename: object, summary: object}}
 */
export function modelCompatibility(store, modelLibraryRecords) {
  const ctx = store && store.runContext;
  const workflow = (ctx && ctx.workflow) || {};
  const version = (ctx && ctx.version) || {};
  const wfModels = Array.isArray(workflow.compatible_models) ? workflow.compatible_models : [];
  const verModels = Array.isArray(version.compatible_models) ? version.compatible_models : [];
  const compatibleFilenames = [...new Set([...wfModels, ...verModels].map(String))];

  const byFilename = {};
  for (const filename of compatibleFilenames) {
    const rec = _findLibraryRecord(modelLibraryRecords, filename);
    byFilename[filename] = {
      compatible: true,
      installed: rec ? (rec.installed === true || rec.state === "installed") : false,
    };
  }

  // Model-role enum options not in compatible_models are known-incompatible.
  const schema = getControlSchema(store);
  for (const entry of Object.values(schema)) {
    if (!entry || typeof entry !== "object") continue;
    if (!_isModelRoleEntry(entry)) continue;
    if (Array.isArray(entry.enum_options) && entry.enum_options.length) {
      for (const opt of entry.enum_options) {
        const key = String(opt);
        if (!Object.prototype.hasOwnProperty.call(byFilename, key)) {
          byFilename[key] = { compatible: false };
        }
      }
    }
  }

  const entries = Object.values(byFilename);
  const compatible = entries.filter((c) => c.compatible);
  const summary = {
    total: entries.length,
    compatible: compatible.length,
    incompatible: entries.length - compatible.length,
    installed: compatible.filter((c) => c.installed).length,
    missing: compatible.filter((c) => !c.installed).length,
  };
  return { byFilename, summary };
}

/** Model-role entries are the "file" controls (see studio_domain/graph.py). */
function _isModelRoleEntry(entry) {
  if (entry.control_kind === "file") return true;
  const dataType = typeof entry.data_type === "string" ? entry.data_type.toUpperCase() : "";
  return dataType === "MODEL" || dataType === "CHECKPOINT" || dataType === "UNET" ||
    dataType === "VAE" || dataType === "CLIP" || dataType === "LORA" ||
    dataType === "CONTROLNET" || dataType === "EMBEDDING";
}

/** Match a model library record by filename (or folder/filename). */
function _findLibraryRecord(records, filename) {
  if (!Array.isArray(records)) return null;
  const target = String(filename);
  return records.find((rec) => {
    if (!rec || typeof rec !== "object") return false;
    if (rec.filename != null && String(rec.filename) === target) return true;
    if (rec.display_name != null && String(rec.display_name) === target) return true;
    if (rec.folder != null && rec.filename != null &&
        String(rec.filename).endsWith(target)) return true;
    return false;
  }) || null;
}

// ── Handoff ───────────────────────────────────────────────────────────────

/**
 * Consume a one-shot workflow handoff (from the Workflows page) and apply it
 * when every referenced entity exists in the loaded data. Never silently
 * substitutes: missing entities produce an error for the caller to surface.
 * @param {object} store
 * @returns {{ok: boolean, error?: string, handoff?: object}}
 */
export function resolveHandoffSelection(store) {
  const handoff = takeWorkflowHandoff();
  if (!handoff || !handoff.workflowId) {
    return { ok: false, error: "no handoff selection" };
  }
  const missing = "Requested workflow/version/preset no longer available";

  const workflow = (store.library || []).find((w) => String(w.workflow_id) === String(handoff.workflowId));
  if (!workflow) return { ok: false, error: missing };

  if (handoff.workflowVersionId) {
    const version = (store.versions || []).find((v) => String(v.workflow_version_id) === String(handoff.workflowVersionId));
    if (!version) return { ok: false, error: missing };
  }
  if (handoff.presetId) {
    const preset = (store.presets || []).find((p) => String(p.preset_id) === String(handoff.presetId));
    if (!preset) return { ok: false, error: missing };
  }

  // Apply: only non-empty handoff ids override, so absent optional ids keep
  // whatever selection the caller already resolved.
  if (handoff.workflowId) store.setWorkflowId(handoff.workflowId);
  if (handoff.workflowVersionId) store.setVersionId(handoff.workflowVersionId);
  if (handoff.presetId) store.setPresetId(handoff.presetId);
  if (handoff.workflowName) store.setWorkflowName(handoff.workflowName);
  if (handoff.presetName) store.setPresetName(handoff.presetName);
  store.setHandoff(handoff);
  return { ok: true, handoff };
}
