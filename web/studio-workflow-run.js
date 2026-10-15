// Modal Studio ΓÇö Workflow Run Frontend Logic
//
// Frontend logic + state for the Studio Workflow ΓåÆ Playground flow:
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
  listWorkflowVersions,
  getWorkflowRunContext,
} from "./studio-backend-api.js";
import { listCachedWorkflows } from "./studio-workflow-picker.js";
import { normalizeWorkflowType } from "./studio-bindable-inputs.js";

import {
  saveWorkflowSelection,
  loadWorkflowSelection,
  clearWorkflowSelection,
  saveWorkflowHandoff,
  takeWorkflowHandoff,
  saveSkipTextGenerate,
  loadSkipTextGenerate,
} from "./studio-playground-state.js";

// Re-export persistence so consumers only need this one module.
export {
  saveWorkflowSelection,
  loadWorkflowSelection,
  clearWorkflowSelection,
  saveWorkflowHandoff,
  takeWorkflowHandoff,
  saveSkipTextGenerate,
  loadSkipTextGenerate,
};

// localStorage keys owned by studio-playground-state.js (kept in sync).
export const PERSISTENCE_KEYS = {
  workflowSelection: "comfymodal.studio.playground.workflow.v1",
  workflowHandoff: "comfymodal.studio.playground.workflow-handoff.v1",
};

export function resolveWorkflowType(store) {
  const ctx = (store && store.runContext) || {};
  const workflow = ctx.workflow || {};
  const version = ctx.version || {};
  const raw = ctx.workflow_type || ctx.workflowType || ctx.type
    || workflow.workflow_type || workflow.workflowType || workflow.type
    || version.workflow_type || version.workflowType
    || (store && (store.workflowType || store.featureId))
    || "t2i";
  return normalizeWorkflowType(raw);
}

export function resolveFeatureId(store) {
  const type = resolveWorkflowType(store);
  if (type === "t2i") return "txt2img";
  return type;
}

// ΓöÇΓöÇ Store ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

/**
 * Create a fresh workflow-run store.
 * @returns {object} Plain mutable state + setter methods.
 */
export function createWorkflowRunStore() {
  return {
    workflowId: "",
    workflowVersionId: "",
    workflowName: "",
    library: [],
    versions: [],
    runContext: null,
    controlValues: {},
    skipTextGenerate: false,
    status: "idle",
    error: "",
    reasons: [],
    handoff: null,
    lastLoadedAt: 0,

    setWorkflowId(id) { this.workflowId = id != null ? String(id) : ""; },
    setVersionId(id) { this.workflowVersionId = id != null ? String(id) : ""; },
    setWorkflowName(name) { this.workflowName = name != null ? String(name) : ""; },
    setControlValue(role, value) { this.controlValues[role] = value; },
    setControlValues(dict) {
      this.controlValues = dict && typeof dict === "object" ? { ...dict } : {};
    },
    setRunContext(ctx) { this.runContext = ctx || null; },
    setSkipTextGenerate(value) { this.skipTextGenerate = value === true; },
    setLibrary(arr) { this.library = Array.isArray(arr) ? arr.slice() : []; },
    setVersions(arr) { this.versions = Array.isArray(arr) ? arr.slice() : []; },
    setStatus(s) { this.status = s || "idle"; },
    setError(e) { this.error = e != null ? String(e) : ""; },
    setReasons(arr) { this.reasons = Array.isArray(arr) ? arr.map(String) : []; },
    setHandoff(h) { this.handoff = h && typeof h === "object" ? { ...h } : null; },

    reset() {
      this.workflowId = "";
      this.workflowVersionId = "";
      this.workflowName = "";
      this.library = [];
      this.versions = [];
      this.runContext = null;
      this.controlValues = {};
      this.skipTextGenerate = false;
      this.status = "idle";
      this.error = "";
      this.reasons = [];
      this.handoff = null;
      this.lastLoadedAt = 0;
    },
  };
}

// ΓöÇΓöÇ Small helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function _errorMessage(err, fallback) {
  if (err == null) return fallback;
  if (typeof err === "string") return err;
  if (err.message) return String(err.message);
  try { return JSON.stringify(err); } catch (e) { return fallback; }
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
 * version state plus local completeness (mapping presence).
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
  return reasons;
}

/** Entry default when the graph does not define a value. */
function _entryDefault(entry) {
  if (Array.isArray(entry.enum_options) && entry.enum_options.length) {
    return entry.required ? entry.enum_options[0] : undefined;
  }
  if (entry.control_kind === "boolean") return false;
  if (entry.minimum != null) return entry.minimum;
  return undefined;
}

// ΓöÇΓöÇ Library / selection loading ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

/**
 * Load the workflow library into the store. Never throws.
 * @param {string} apiBase
 * @param {object} store
 * @returns {Promise<Array>}
 */
export async function loadWorkflowLibrary(apiBase, store) {
  try {
    const data = await listCachedWorkflows(apiBase);
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
  // Request-generation guard: rapid actual type switching fires overlapping
  // selections. A stale response must not overwrite the store the newer
  // selection now owns — compare against the live workflow id captured at
  // entry before applying anything.
  var _reqWf = workflowId != null ? String(workflowId) : "";
  try {
    const data = await getWorkflowRunContext(apiBase, workflowId, versionId);
    if (_reqWf && store && String(store.workflowId || "") !== _reqWf) {
      return { ok: false, error: "superseded", reasons: ["superseded"], superseded: true };
    }
    if (!data || data.status !== "ok") {
      const msg = (data && (data.message || data.error)) || "failed to load run context";
      store.setStatus("error");
      store.setError(msg);
      store.setReasons([msg]);
      return { ok: false, error: msg, reasons: [msg] };
    }
    const version = data.version;
    if (!version || !version.state) {
      const stateReasons = data.state && Array.isArray(data.state.reasons)
        ? data.state.reasons.map(String)
        : [];
      const noVersions = stateReasons.includes("no versions");
      const msg = noVersions ? "workflow has no versions" : "run context missing version state";
      store.setStatus("error");
      store.setError(msg);
      store.setReasons(stateReasons.length ? stateReasons : [msg]);
      return { ok: false, error: msg, reasons: stateReasons.length ? stateReasons : [msg], noVersions };
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
 * Select a workflow: reset version state, load the current run-context (with
 * a versions-list fallback when the current version is unavailable), and
 * derive control defaults from the resolved version.
 * @param {string} apiBase
 * @param {object} store
 * @param {string} workflowId
 * @returns {Promise<{ok: boolean, error?: string, reasons?: string[]}>}
 */
export async function selectWorkflow(apiBase, store, workflowId) {
  // Monotonic selection generation: each new selection supersedes older
  // in-flight ones. Checked after every await so a slow loser returns a
  // marked failure instead of overwriting the winner's store — callers
  // ignore superseded results without clobbering status or selection.
  var _gen = (store._selGen = ((store._selGen || 0) + 1));
  function _stale() { return store._selGen !== _gen; }
  function _superseded() { return { ok: false, error: "superseded", reasons: ["superseded"], superseded: true }; }
  store.setStatus("loading");
  store.setError("");
  try {
    if (!workflowId) {
      store.setStatus("error");
      store.setError("no workflow selected");
      store.setReasons(["no workflow selected"]);
      return { ok: false, error: "no workflow selected", reasons: ["no workflow selected"] };
    }
    // Reset version state from any previous selection.
    store.setVersionId("");
    store.setRunContext(null);
    store.controlValues = {};
    store.setSkipTextGenerate(false);
    store.setWorkflowId(workflowId);

    const wf = (store.library || []).find((w) => String(w.workflow_id) === String(workflowId));
    const latestVersionId = wf && wf.latest_version_id;
    let ctxResult = null;

    // The library row already identifies the current version. Use the bundle
    // directly in the common case; it contains the version state and mapping
    // that the separate versions request would only repeat.
    if (latestVersionId) {
      ctxResult = await loadRunContext(apiBase, store, workflowId, latestVersionId);
      if (_stale() || (ctxResult && ctxResult.superseded)) return _superseded();
      if (ctxResult.ok) {
        const loadedVersion = store.runContext && store.runContext.version;
        store.setVersions(loadedVersion ? [loadedVersion] : []);
      } else if (!ctxResult.noVersions) {
        store.setStatus("error");
        return { ok: false, error: ctxResult.error, reasons: ctxResult.reasons };
      }
    }

    // A missing library latest id, or a run-context response that explicitly
    // reports no versions, still needs the history list to choose a version.
    if (!ctxResult || !ctxResult.ok) {
      const versionsData = await listWorkflowVersions(apiBase, workflowId);
      if (_stale()) return _superseded();
      const versions = (versionsData && Array.isArray(versionsData.versions)) ? versionsData.versions : [];
      store.setVersions(versions);

      if (!versions.length) {
        store.setStatus("error");
        store.setError("workflow has no versions");
        store.setReasons(["no versions"]);
        return { ok: false, error: "workflow has no versions", reasons: ["no versions"] };
      }

      const versionId = _pickDefaultVersionId(versions, latestVersionId);
      if (!versionId) {
        store.setStatus("error");
        store.setError("workflow has no runnable version");
        store.setReasons(["no versions"]);
        return { ok: false, error: "workflow has no runnable version", reasons: ["no versions"] };
      }
      ctxResult = await loadRunContext(apiBase, store, workflowId, versionId);
      if (_stale() || (ctxResult && ctxResult.superseded)) return _superseded();
    }

    if (!ctxResult.ok) {
      store.setStatus("error");
      return { ok: false, error: ctxResult.error, reasons: ctxResult.reasons };
    }

    // Control defaults come from the version's own captured graph.
    store.controlValues = defaultValuesFromContext(store);
    store.setSkipTextGenerate(loadSkipTextGenerate(workflowId, store.workflowVersionId));
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
 * Select a version of the current workflow: reload run-context
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
    store.controlValues = {};
    store.setSkipTextGenerate(false);

    const ctxResult = await loadRunContext(apiBase, store, store.workflowId, versionId);
    // A tool switch cleared the store mid-flight: loadRunContext reports
    // superseded via its workflow-id guard. Pass it through (never convert
    // to an error) so callers yield to the newer tool instead of showing
    // "superseded" or clobbering the new selection.
    if (ctxResult && ctxResult.superseded) return ctxResult;
    if (!ctxResult.ok) {
      store.setStatus("error");
      return { ok: false, error: ctxResult.error, reasons: ctxResult.reasons };
    }

    store.controlValues = defaultValuesFromContext(store);
    store.setSkipTextGenerate(loadSkipTextGenerate(store.workflowId, versionId));
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
 * Reset control values to the version's graph defaults. There is no preset to
 * select; the workflow version is self-describing.
 * @param {object} store
 * @returns {Promise<{ok: boolean, error?: string, reasons?: string[]}>}
 */
export async function selectVersionDefaults(store) {
  store.setStatus("loading");
  store.setError("");
  try {
    store.controlValues = defaultValuesFromContext(store);
    store.setReasons(_gateReasons(store));
    store.lastLoadedAt = Date.now();
    store.setStatus("ready");
    return { ok: true };
  } catch (err) {
    const msg = _errorMessage(err, "failed to load version defaults");
    store.setStatus("error");
    store.setError(msg);
    store.setReasons([msg]);
    return { ok: false, error: msg, reasons: [msg] };
  }
}

// ΓöÇΓöÇ Schema / defaults ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

/**
 * The control schema (semantic_role ΓåÆ mapping entry) from the cached
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
 * graph current value (verbatim, including 0 / 0.0 / false / "") ΓåÆ entry
 * default. Values that cannot be resolved are left unset (backend decides).
 * Never invents values outside graph-declared options.
 * @param {object} store
 * @returns {object} { role: value }
 */
export function defaultValuesFromContext(store) {
  const schema = getControlSchema(store);
  const executable = store && store.runContext && store.runContext.version
    ? store.runContext.version.executable_prompt
    : null;
  const values = {};
  for (const [role, entry] of Object.entries(schema)) {
    if (!entry || typeof entry !== "object") continue;
    let value;
    if (executable) {
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

// ΓöÇΓöÇ Validation ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

/**
 * Image Tool Inputs (Source Image, Mask) reference files by name. The input
 * directory changes on every upload, so a captured enum snapshot of its
 * contents is never a closed vocabulary — membership must not gate these.
 */
export function isImageControlRole(key, entry) {
  if (key === "source_image" || key === "mask") return true;
  const kind = entry && entry.control_kind;
  return kind === "image";
}

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
    if (!isImageControlRole(key, entry)
      && Array.isArray(entry.enum_options) && entry.enum_options.length && present) {
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
 * Merge graph-derived defaults with caller overrides and validate the result.
 * @param {object} defaults
 * @param {object} overrides
 * @param {object} controlSchema
 * @returns {{values: object, errors: Array<{field: string, message: string}>}}
 */
export function mergeDefaultsAndOverrides(defaults, overrides, controlSchema) {
  const base = defaults && typeof defaults === "object" ? defaults : {};
  const merged = { ...base, ...(overrides && typeof overrides === "object" ? overrides : {}) };
  return validateMappedValues(merged, controlSchema);
}

/**
 * Runnable gating: backend state reasons (verbatim) + mapping/control
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
  const schema = getControlSchema(store);
  const { errors } = validateMappedValues(store.controlValues || {}, schema);
  if (errors.length) {
    runnable = false;
    reasons.push(errors[0].message);
  }
  return { runnable, reasons };
}

/**
 * Keep the client gate aligned with the backend's authoritative bundle
 * resolver (studio_workflow_run.resolve_workflow_run_bundle with
 * remote_model_readiness=True). A remote Golden target resolves models in the
 * deployed Modal volume, so host-local "missing model ..." reasons must not
 * block it; every other reason stays fail-closed.
 */
export function resolveExecutionRunnable(gated, remoteSelected) {
  if (!gated || gated.runnable || !remoteSelected) return gated;
  const reasons = Array.isArray(gated.reasons) ? gated.reasons : [];
  const kept = reasons.filter((r) => !String(r).startsWith("missing model "));
  if (kept.length === reasons.length) return gated;
  return { runnable: kept.length === 0, reasons: kept };
}

// ΓöÇΓöÇ Run payload ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

/**
 * Build the run payload. Controls contain ONLY schema-known roles. Callers
 * must run validation first (resolveRunnable / mergeDefaultsAndOverrides);
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
  const workflowType = resolveWorkflowType(store);
  return {
    workflow_id: store.workflowId,
    workflow_version_id: store.workflowVersionId,
    featureId: resolveFeatureId(store),
    workflow_type: workflowType,
    controls: values,
    modal_options: {
      ...(modalOptions && typeof modalOptions === "object" ? modalOptions : {}),
      skip_text_generate: store.skipTextGenerate === true,
    },
    metadata: {
      source: "studio_playground",
      workflow_id: store.workflowId,
      workflow_version_id: store.workflowVersionId,
      workflow_name: store.workflowName || "",
      workflow_hash: (version && version.graph_hash) || null,
      workflow_type: workflowType,
    },
    trace: trace && typeof trace === "object" ? trace : {},
  };
}

// ΓöÇΓöÇ Model compatibility ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

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

// ΓöÇΓöÇ Handoff ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

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
  const missing = "Requested workflow/version no longer available";

  const workflow = (store.library || []).find((w) => String(w.workflow_id) === String(handoff.workflowId));
  if (!workflow) return { ok: false, error: missing };

  if (handoff.workflowVersionId) {
    const version = (store.versions || []).find((v) => String(v.workflow_version_id) === String(handoff.workflowVersionId));
    if (!version) return { ok: false, error: missing };
  }

  // Apply: only non-empty handoff ids override, so absent optional ids keep
  // whatever selection the caller already resolved.
  if (handoff.workflowId) store.setWorkflowId(handoff.workflowId);
  if (handoff.workflowVersionId) store.setVersionId(handoff.workflowVersionId);
  if (handoff.workflowName) store.setWorkflowName(handoff.workflowName);
  store.setHandoff(handoff);
  return { ok: true, handoff };
}

// ── References (Phase 8, Lane C) ───────────────────────────────────────
//
// Ordered reference collection, separate from ordinary mapped controls.
// Frozen method ids mirror studio_domain/models.py REFERENCE_METHOD_IDS
// (no Auto/best-available anywhere). Structural bindings live in the
// Mapping (Lane A: mapping.reference_method + mapping.reference_bindings);
// card values live per workflow+version in studio-playground-state.js;
// this module owns the pure glue: capability reads, method-vs-binding
// compatibility, card list helpers, validation, and the studio_references
// run companion. No DOM, no storage, no fetch — fully node-testable.

/** Frozen reference method ids. Never rename: Mapping, companion, prefs. */
export const REFERENCE_METHODS = Object.freeze([
  "conditioning_slots",
  "reference_latent_chain",
  "dedicated",
]);

export const REFERENCE_METHOD_LABELS = Object.freeze({
  conditioning_slots: "Conditioning slots",
  reference_latent_chain: "Reference latent chain",
  dedicated: "Dedicated reference workflow",
});

export function referenceMethodLabel(id) {
  return REFERENCE_METHOD_LABELS[id] || String(id || "reference method");
}

/** Stable internal card id. Display numbering always follows array order. */
export function makeReferenceCardId() {
  const rand = Math.floor(Math.random() * Math.pow(36, 6)).toString(36);
  return "ref_" + Date.now().toString(36) + "_" + rand;
}

/**
 * Normalize a raw card list into [{id, file, label}]. Non-objects drop;
 * missing ids are generated (stability comes from persisting the result).
 * Never invents image files: file degrades to "".
 */
export function sanitizeReferenceCards(raw) {
  if (!Array.isArray(raw)) return [];
  const out = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const id = typeof item.id === "string" && item.id ? item.id.slice(0, 80) : makeReferenceCardId();
    out.push({
      id,
      file: typeof item.file === "string" ? item.file.slice(0, 500) : "",
      label: typeof item.label === "string" ? item.label.slice(0, 80) : "",
    });
  }
  return out;
}

/** Append a card. Returns a new array; never mutates the input. */
export function addReferenceCard(cards, card) {
  const list = sanitizeReferenceCards(cards);
  const next = sanitizeReferenceCards([card && typeof card === "object" ? card : {}]);
  list.push(next[0] || { id: makeReferenceCardId(), file: "", label: "" });
  return list;
}

/** Remove a card by id. Returns a new array; unknown ids leave it unchanged. */
export function removeReferenceCard(cards, id) {
  const list = sanitizeReferenceCards(cards);
  const key = id != null ? String(id) : "";
  const next = list.filter((c) => c.id !== key);
  return next.length === list.length ? list : next;
}

/**
 * Move a card earlier (delta < 0) or later (delta > 0). Clamps at the ends;
 * unknown ids leave the order unchanged. Returns a new array.
 */
export function moveReferenceCard(cards, id, delta) {
  const list = sanitizeReferenceCards(cards);
  const key = id != null ? String(id) : "";
  const at = list.findIndex((c) => c.id === key);
  if (at === -1) return list;
  const step = Number(delta) || 0;
  if (!step) return list;
  const to = Math.max(0, Math.min(list.length - 1, at + (step < 0 ? -1 : 1) * Math.min(Math.abs(step), list.length)));
  if (to === at) return list;
  const [card] = list.splice(at, 1);
  list.splice(to, 0, card);
  return list;
}

function _normalizeReferenceSlots(bindings) {
  const raw = bindings && typeof bindings === "object" ? bindings.slots : null;
  const list = Array.isArray(raw) ? raw : [];
  const out = [];
  for (const entry of list) {
    if (!entry || typeof entry !== "object") continue;
    const nodeId = entry.node_id != null ? String(entry.node_id) : "";
    const socket = entry.socket != null ? String(entry.socket) : "";
    if (!nodeId || !socket) continue;
    let order = Number(entry.order);
    if (!Number.isFinite(order)) order = out.length;
    out.push({
      node_id: nodeId,
      socket,
      kind: entry.kind === "source" ? "source" : "reference",
      order,
    });
  }
  out.sort((a, b) => a.order - b.order);
  out.forEach((slot, i) => { slot.order = i; });
  return out;
}

/** Locate the Mapping node carrying reference bindings (tolerates nesting). */
function _referenceMappingNode(store) {
  const ctx = store && typeof store === "object" ? store.runContext : null;
  if (!ctx || typeof ctx !== "object") return null;
  const direct = ctx.mapping;
  if (direct && typeof direct === "object") {
    if ("reference_method" in direct || "reference_bindings" in direct) return direct;
    const nested = direct.mapping;
    if (nested && typeof nested === "object"
      && ("reference_method" in nested || "reference_bindings" in nested)) {
      return nested;
    }
    return direct;
  }
  const version = ctx.version;
  const versionMapping = version && typeof version === "object" ? version.mapping : null;
  if (versionMapping && typeof versionMapping === "object") return versionMapping;
  return null;
}

/**
 * Server capability for references (Lane A contract), read-only.
 * Unbound versions yield boundMethod "" — callers block with a reason
 * instead of inferring anything.
 */
export function resolveReferenceCapability(store) {
  const node = _referenceMappingNode(store);
  if (!node) {
    return {
      hasMapping: false, boundMethod: "", bindings: null,
      slots: [], refSlots: [], chain: null, dedicatedTarget: "",
    };
  }
  const rawMethod = typeof node.reference_method === "string" ? node.reference_method : "";
  const boundMethod = REFERENCE_METHODS.indexOf(rawMethod) !== -1 ? rawMethod : "";
  const bindings = node.reference_bindings && typeof node.reference_bindings === "object"
    ? node.reference_bindings
    : null;
  const slots = _normalizeReferenceSlots(bindings);
  const chain = bindings && bindings.chain && typeof bindings.chain === "object" ? bindings.chain : null;
  const dedicatedTarget = bindings && bindings.dedicated_target != null
    ? String(bindings.dedicated_target) : "";
  return {
    hasMapping: true, boundMethod, bindings,
    slots, refSlots: slots.filter((s) => s.kind === "reference"),
    chain, dedicatedTarget,
  };
}

/**
 * Compatibility of the remembered explicit method against the version's
 * bound method. supported=false keeps the remembered selection visible —
 * callers show reason and block; they never auto-switch or truncate.
 */
export function resolveReferenceMethodState(store, prefs) {
  const capability = resolveReferenceCapability(store);
  let method = prefs && typeof prefs.referenceMethod === "string" ? prefs.referenceMethod : "";
  if (REFERENCE_METHODS.indexOf(method) === -1) method = "";
  if (!capability.hasMapping || !capability.boundMethod) {
    return {
      method, boundMethod: "", supported: false,
      reason: "This workflow version has no reference bindings — bind a Reference Method in the Workflow Setup Wizard.",
      capability,
    };
  }
  if (!method) {
    return { method: "", boundMethod: capability.boundMethod, supported: false, reason: "", capability };
  }
  if (method !== capability.boundMethod) {
    return {
      method, boundMethod: capability.boundMethod, supported: false,
      reason: "Reference method '" + referenceMethodLabel(method) + "' is not bound in this workflow version "
        + "(bound: '" + referenceMethodLabel(capability.boundMethod) + "'). "
        + "Switch the Reference Method or rebind in the Workflow Setup Wizard.",
      capability,
    };
  }
  if (method === "conditioning_slots" && capability.refSlots.length === 0) {
    return {
      method, boundMethod: capability.boundMethod, supported: false,
      reason: "Conditioning slots is bound but exposes no reference slots in this version.",
      capability,
    };
  }
  return { method, boundMethod: capability.boundMethod, supported: true, reason: "", capability };
}

/**
 * Known client-side capacity for a supported method, or null when the
 * method is repeatable/server-ruled (chain repeats its branch; dedicated
 * follows the override workflow). Never invents a number.
 */
export function referenceCapacityFor(methodState) {
  if (!methodState || !methodState.supported) return null;
  if (methodState.method === "conditioning_slots") {
    return methodState.capability ? methodState.capability.refSlots.length : null;
  }
  return null;
}

/** Concrete per-card slot label for a supported method ("" otherwise). */
export function referenceSlotLabel(methodState, index) {
  if (!methodState || !methodState.supported) return "";
  const i = Number(index) || 0;
  if (methodState.method === "conditioning_slots") {
    const slot = methodState.capability ? methodState.capability.refSlots[i] : null;
    if (!slot) return "Beyond capacity";
    return "Slot " + (i + 1) + " · " + slot.node_id + ":" + slot.socket;
  }
  if (methodState.method === "reference_latent_chain") return "Chain link " + (i + 1);
  if (methodState.method === "dedicated") return "Input " + (i + 1);
  return "";
}

/**
 * Validate cards against a method state. images follows card order
 * (payload order); errors are specific user-facing reasons.
 */
export function validateReferenceCards(cards, methodState) {
  const list = sanitizeReferenceCards(cards);
  const errors = [];
  const images = [];
  list.forEach((card, i) => {
    if (!card.file) {
      errors.push("Reference " + (i + 1) + " has no image — pick one or remove the card.");
    } else {
      images.push(card.file);
    }
  });
  const capacity = referenceCapacityFor(methodState);
  if (capacity != null && list.length > capacity) {
    errors.push("This version exposes " + capacity + " reference slot"
      + (capacity === 1 ? "" : "s") + " for "
      + referenceMethodLabel(methodState && methodState.method)
      + " — remove " + (list.length - capacity) + " card"
      + (list.length - capacity === 1 ? "" : "s") + ".");
  }
  return { cards: list, images, errors };
}

/**
 * Build the studio_references run companion, mirroring the server builder
 * shape (studio_domain/models.py build_studio_references_companion) plus
 * the client-known ordered image refs the server leaves empty. Fail-closed:
 * null unless the method is supported, dedicated has its override, every
 * card carries a file, and at least one card exists — never a partial or
 * inferred submit.
 *
 * Named companion (not buildReferencePayload): that name already builds the
 * Wizard→Mapping payload in studio-bindable-inputs.js.
 */
export function buildStudioReferencesCompanion(store, cards, prefs) {
  const methodState = resolveReferenceMethodState(store, prefs);
  if (!methodState.supported || !methodState.method) return null;
  const { images, errors } = validateReferenceCards(cards, methodState);
  if (errors.length || !images.length) return null;
  const list = sanitizeReferenceCards(cards);
  const dedicatedTarget = methodState.method === "dedicated"
    ? String((prefs && prefs.referenceOverride) || "")
    : "";
  if (methodState.method === "dedicated" && !dedicatedTarget) return null;
  // Executing identity: generic methods execute the origin workflow; a
  // dedicated override executes the override workflow (its version resolves
  // server-side — "" here means unknown, never a guess). Mirrors the Lane D
  // snapshot keys so Lane B normalizes without inventing identity.
  const originWorkflowId = (store && store.workflowId) || "";
  const originVersionId = (store && store.workflowVersionId) || "";
  const executingWorkflowId = methodState.method === "dedicated" ? dedicatedTarget : originWorkflowId;
  const executingVersionId = methodState.method === "dedicated" ? "" : originVersionId;
  return {
    method: methodState.method,
    origin_workflow_id: originWorkflowId,
    origin_version_id: originVersionId,
    executing_workflow_id: executingWorkflowId,
    executing_version_id: executingVersionId,
    dedicated_target: dedicatedTarget,
    card_ids: list.map((c) => c.id),
    images,
    provenance: { source: "studio" },
  };
}

// ── Canvas /prompt fail-closed reference gate (Phase 8) ─────────────────
//
// Pure helpers for the fetchApi patch in web/modal-node.js. The ComfyUI
// topbar RUN posts the raw canvas graph to POST /prompt, bypassing the
// Studio shelf RUN (which carries studio_references). When references are
// engaged for the selected workflow — a reference method is chosen OR at
// least one reference card exists (mirroring _studioReferenceGate in
// web/studio-playground.js) — a canvas /prompt without a reference payload
// must fail closed with an honest error instead of silently running
// without the configured references. All three functions are pure
// (explicit args, no window/localStorage/DOM) and never throw.

/**
 * Read whether Studio References are engaged for the selected workflow.
 * Engaged = a non-empty referenceMethod for the workflow id OR >= 1 card
 * stored under "workflowId::versionId" (mirrors _studioReferenceGate).
 * @param {{workflowId?: string, workflowVersionId?: string}|null} selection
 * @param {object|null} methodsMap - { [workflowId]: { referenceMethod } }
 * @param {object|null} referencesMap - { ["wid::ver"]: [{id,file,label}] }
 * @returns {{workflowId: string, versionId: string, method: string, cardCount: number, files: string[]}|null}
 */
export function readReferenceEngagement(selection, methodsMap, referencesMap) {
  try {
    const workflowId = selection && typeof selection.workflowId === "string"
      ? selection.workflowId
      : "";
    if (!workflowId) return null;
    const versionId = selection && typeof selection.workflowVersionId === "string"
      ? selection.workflowVersionId
      : "";
    const methodEntry = methodsMap && typeof methodsMap === "object"
      ? methodsMap[workflowId]
      : null;
    const rawMethod = methodEntry && typeof methodEntry === "object"
      && typeof methodEntry.referenceMethod === "string"
      ? methodEntry.referenceMethod
      : "";
    const method = rawMethod.trim() ? rawMethod : "";
    const key = workflowId + "::" + versionId;
    const rawCards = referencesMap && typeof referencesMap === "object"
      ? referencesMap[key]
      : null;
    const cards = Array.isArray(rawCards) ? rawCards : [];
    if (!method && cards.length === 0) return null;
    const files = [];
    for (const card of cards) {
      if (card && typeof card === "object"
        && typeof card.file === "string" && card.file) {
        files.push(card.file);
      }
    }
    return { workflowId, versionId, method, cardCount: cards.length, files };
  } catch (_e) {
    return null;
  }
}

/**
 * True when an outgoing /prompt body already carries a reference payload.
 * @param {*} parsed - parsed /prompt request body
 * @returns {boolean}
 */
export function promptCarriesReferences(parsed) {
  try {
    if (!parsed || typeof parsed !== "object") return false;
    const viaExtra = parsed.extra_data && typeof parsed.extra_data === "object"
      ? parsed.extra_data.studio_references
      : undefined;
    if (viaExtra !== null && viaExtra !== undefined && typeof viaExtra === "object") return true;
    const viaTop = parsed.studio_references;
    if (viaTop !== null && viaTop !== undefined && typeof viaTop === "object") return true;
    return false;
  } catch (_e) {
    return false;
  }
}

/**
 * Honest block message for a canvas /prompt stopped by the reference gate.
 * Names the workflow id, the method (or "reference cards"), the card count,
 * and both remedies (Run from Studio References, or clear method/cards).
 * @param {{workflowId?: string, method?: string, cardCount?: number}|null} engagement
 * @returns {string}
 */
export function referenceBlockMessage(engagement) {
  try {
    const eng = engagement && typeof engagement === "object" ? engagement : {};
    const workflowId = typeof eng.workflowId === "string" && eng.workflowId
      ? eng.workflowId
      : "unknown";
    const count = Number(eng.cardCount);
    const cardCount = Number.isFinite(count) && count >= 0 ? Math.floor(count) : 0;
    const method = typeof eng.method === "string" && eng.method
      ? "method '" + eng.method + "'"
      : "reference cards";
    const cardWord = cardCount === 1 ? "1 reference card" : cardCount + " reference cards";
    return "Studio References are engaged for workflow '" + workflowId + "' ("
      + method + ", " + cardWord + ") but this canvas run carries no reference "
      + "payload — blocked instead of silently running without references. "
      + "Run from Studio References, or clear the reference method/cards and run again.";
  } catch (_e) {
    return "Studio References are engaged but this canvas run carries no reference "
      + "payload — blocked instead of silently running without references. "
      + "Run from Studio References, or clear the reference method/cards and run again.";
  }
}

// ── Studio V3 preset overrides (Phase 12, frontend lane) ─────────────────
// Pure, DOM-free helpers so exact-version preset overrides and Playground-
// scoped output options reach the Run path. No storage, no fetch.

/**
 * Apply a preset's core overrides onto the store's control values.
 * Exact-version only: the preset record's workflow_version_id must equal the
 * store's live workflowVersionId, otherwise {ok:false} and the store is
 * untouched (never cross-version apply). Only schema-known roles survive
 * (validated, never coerced); image-control roles are never set from a
 * preset (presets carry no images by contract).
 *
 * @param {object} store workflow-run store
 * @param {object} presetState v1 studio_state (or null for neutral reset)
 * @param {object} opts {expectedVersionId?: string}
 * @returns {{ok: boolean, error?: string, applied?: object}}
 */
export function applyPresetCoreOverrides(store, presetState, opts) {
  if (!store || typeof store !== "object") return { ok: false, error: "no store" };
  const o = opts && typeof opts === "object" ? opts : {};
  const liveVersion = store.workflowVersionId != null ? String(store.workflowVersionId) : "";
  if (o.expectedVersionId != null && String(o.expectedVersionId) !== liveVersion) {
    return { ok: false, error: "preset version mismatch" };
  }
  const schema = getControlSchema(store);
  const core = presetState && typeof presetState === "object" ? presetState.core : null;
  const next = Object.assign({}, store.controlValues || {});
  const applied = {};
  if (core && typeof core === "object") {
    // The visible prompt is mapping-independent core state (not a mapped
    // control): on a stale-mapping version the prompt role is absent from the
    // control schema while scalar roles like seed survive, so gating the
    // prompt on schema membership would leave a stale prompt behind. Always
    // write it — including "" (a preset replace clears the editor; empty must
    // never inherit). The shelf prompt card reads mapping entries rather than
    // the schema, so it shows whatever alias is written here.
    if (typeof core.positive_prompt === "string") {
      const hasSchemaPrompt = !!(schema.positive_prompt || schema.prompt);
      const hasStorePrompt = Object.prototype.hasOwnProperty.call(next, "positive_prompt")
        || Object.prototype.hasOwnProperty.call(next, "prompt");
      // Clearing an absent prompt is a no-op — never invent the key (an
      // unknown empty role would newly fail validation on prompt-less
      // versions). A present value always writes (mapping-independent core).
      if (core.positive_prompt !== "" || hasSchemaPrompt || hasStorePrompt) {
        const role = schema.positive_prompt ? "positive_prompt" : schema.prompt ? "prompt"
          : Object.prototype.hasOwnProperty.call(next, "positive_prompt") ? "positive_prompt"
          : "prompt";
        if (!isImageControlRole(role, schema[role])) {
          next[role] = core.positive_prompt;
          applied[role] = core.positive_prompt;
        }
      }
    }
    if (typeof core.negative_prompt === "string") {
      if (schema.negative_prompt) {
        next.negative_prompt = core.negative_prompt;
        applied.negative_prompt = core.negative_prompt;
      } else if (core.negative_prompt === "") {
        // Clearing must also reach a store holding the role under no schema.
        delete next.negative_prompt;
      }
    }
    const overrides = core.controls && typeof core.controls === "object" ? core.controls : {};
    for (const role of Object.keys(overrides)) {
      if (!Object.prototype.hasOwnProperty.call(schema, role)) continue;
      if (isImageControlRole(role, schema[role])) continue;
      next[role] = overrides[role];
      applied[role] = overrides[role];
    }
  }
  const { values } = validateMappedValues(next, schema);
  store.controlValues = values;
  // Intentionally applied prompt aliases survive validation even when the
  // schema lost the role (stale mapping): the editor reads them back, and the
  // run-payload builder re-validates, so nothing schema-unknown is ever sent.
  for (const role of ["prompt", "positive_prompt"]) {
    if (
      Object.prototype.hasOwnProperty.call(applied, role)
      && typeof store.controlValues[role] !== "string"
    ) {
      store.controlValues = { ...store.controlValues, [role]: applied[role] };
    }
  }
  return { ok: true, applied };
}

/**
 * Resolve the effective output options for a Run: global base options with
 * the preset's Playground-scoped output override applied. The preset section
 * is the FLAT contract shape (output_format, quality, auto_save_local,
 * save_folder, save_metadata_sidecar, preview_* scalars). The override never
 * persists globally (no POST, no localStorage write here) — it rides the
 * single run payload only. Unknown override keys are dropped.
 *
 * @param {object} baseOptions global modal options (from the preload cache)
 * @param {object} presetOutput preset output section or null
 * @returns {object} merged options (fresh object; inputs untouched)
 */
export function resolveEffectiveOutputOptions(baseOptions, presetOutput) {
  const base = baseOptions && typeof baseOptions === "object" ? baseOptions : {};
  const merged = Object.assign({}, base);
  const over = presetOutput && typeof presetOutput === "object" ? presetOutput : null;
  if (!over) return merged;
  if (typeof over.output_format === "string" && over.output_format) {
    merged.output_format = over.output_format;
  }
  if (typeof over.quality === "number" && Number.isFinite(over.quality)) {
    merged.quality = Math.max(1, Math.min(100, Math.floor(over.quality)));
  }
  if (typeof over.auto_save_local === "boolean") merged.auto_save_local = over.auto_save_local;
  if (typeof over.save_folder === "string" && over.save_folder) {
    merged.save_folder = over.save_folder;
  }
  if (typeof over.save_metadata_sidecar === "boolean") {
    merged.save_metadata_sidecar = over.save_metadata_sidecar;
  }
  if (over.preview_default === "on" || over.preview_default === "off") {
    merged.preview_default = over.preview_default;
    merged.data_saver_default = over.preview_default;
  }
  if (typeof over.preview_codec === "string" && over.preview_codec) {
    merged.preview_codec = over.preview_codec;
  }
  if (typeof over.preview_quality === "number" && Number.isFinite(over.preview_quality)) {
    const q = Math.max(1, Math.min(100, Math.floor(over.preview_quality)));
    merged.preview_quality = q;
    merged.data_saver_quality = q;
  }
  return merged;
}
