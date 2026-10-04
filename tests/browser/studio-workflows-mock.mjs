// Modal Studio — Workflow Library Mock API for E2E browser tests
//
// In-memory backend for the Studio Workflows page (web/studio-workflows.js).
//
// Install order contract: call installStudioMockApi(page) FIRST, then this
// mock. Later page.route registrations take precedence, so every
// /comfymodal/studio/workflows* request is answered here and the shared
// mock never sees it — api.assertNoUnhandledCalls() stays clean.
//
// Every handled request is recorded into state.calls as
//   { method, path, body }
// so specs can assert the exact calls the page made.
//
// Usage:
//   import { installWorkflowsMock } from "./studio-workflows-mock.mjs";
//   const wfMock = await installWorkflowsMock(page);
//   await page.goto(baseURL);   // navigation AFTER install
//
// Self-contained: does NOT import from studio-mock-api.mjs.

import { randomBytes } from "node:crypto";

// ── Small helpers ─────────────────────────────────────────────────────────

function _makeId(prefix) {
  return prefix + randomBytes(6).toString("hex");
}

function _now() {
  return new Date().toISOString();
}

function _json(data, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(data),
  };
}

function _error(message, httpStatus = 400) {
  return _json(
    { status: "error", message, _httpStatus: httpStatus },
    httpStatus
  );
}

/** Convert "/comfymodal/studio/workflows/:id" → { regex, paramNames }. */
function _compilePattern(pattern) {
  const paramNames = [];
  const regex = new RegExp(
    "^" +
      pattern.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, (_, name) => {
        paramNames.push(name);
        return "([^/]+)";
      }) +
      "$"
  );
  return { regex, paramNames };
}

// ── Mapping candidates / seeded mapping entries ──────────────────────────
//
// Shared control schema. The candidates endpoint returns this list verbatim;
// seeded mappings reuse it and add a `value` field so the preset editor has
// deterministic defaults.

const CANDIDATE_ENTRIES = [
  {
    semantic_role: "sampler", node_id: "6", input_name: "sampler_name",
    kind: "node_input", data_type: "COMBO",
    enum_options: ["euler", "euler_ancestral", "dpmpp_2m", "uni_pc"],
    minimum: null, maximum: null, step: null,
    required: true, multiline: false, control_kind: "enum", display_name: "Sampler",
  },
  {
    semantic_role: "scheduler", node_id: "6", input_name: "scheduler",
    kind: "node_input", data_type: "COMBO",
    enum_options: ["normal", "karras", "exponential", "sgm_uniform"],
    minimum: null, maximum: null, step: null,
    required: true, multiline: false, control_kind: "enum", display_name: "Scheduler",
  },
  {
    semantic_role: "seed", node_id: "6", input_name: "seed",
    kind: "node_input", data_type: "INT",
    enum_options: null, minimum: 0, maximum: null, step: 1,
    required: false, multiline: false, control_kind: "integer", display_name: "Seed",
  },
  {
    semantic_role: "steps", node_id: "6", input_name: "steps",
    kind: "node_input", data_type: "INT",
    enum_options: null, minimum: 1, maximum: 150, step: 1,
    required: false, multiline: false, control_kind: "integer", display_name: "Steps",
  },
  {
    semantic_role: "cfg", node_id: "6", input_name: "cfg",
    kind: "node_input", data_type: "FLOAT",
    enum_options: null, minimum: 1, maximum: 30, step: 0.5,
    required: false, multiline: false, control_kind: "number", display_name: "CFG",
  },
  {
    semantic_role: "positive_prompt", node_id: "4", input_name: "text",
    kind: "node_input", data_type: "STRING",
    enum_options: null, minimum: null, maximum: null, step: null,
    required: false, multiline: true, control_kind: "multiline", display_name: "Positive Prompt",
  },
  {
    semantic_role: "negative_prompt", node_id: "5", input_name: "text",
    kind: "node_input", data_type: "STRING",
    enum_options: null, minimum: null, maximum: null, step: null,
    required: false, multiline: true, control_kind: "multiline", display_name: "Negative Prompt",
  },
  {
    semantic_role: "model", node_id: "3", input_name: "ckpt_name",
    kind: "node_input", data_type: "MODEL",
    enum_options: null, minimum: null, maximum: null, step: null,
    required: true, multiline: false, control_kind: "file", display_name: "Model",
  },
  {
    semantic_role: "width", node_id: "2", input_name: "width",
    kind: "node_input", data_type: "INT",
    enum_options: null, minimum: 64, maximum: 2048, step: 8,
    required: false, multiline: false, control_kind: "integer", display_name: "Width",
  },
  {
    semantic_role: "height", node_id: "2", input_name: "height",
    kind: "node_input", data_type: "INT",
    enum_options: null, minimum: 64, maximum: 2048, step: 8,
    required: false, multiline: false, control_kind: "integer", display_name: "Height",
  },
  {
    semantic_role: "denoise", node_id: "6", input_name: "denoise",
    kind: "node_input", data_type: "FLOAT",
    enum_options: null, minimum: 0, maximum: 1, step: 0.01,
    required: false, multiline: false, control_kind: "number", display_name: "Denoise",
  },
  {
    semantic_role: "source_image", node_id: "9", input_name: "image",
    kind: "node_input", data_type: "IMAGE",
    enum_options: null, minimum: null, maximum: null, step: null,
    required: false, multiline: false, control_kind: "image", display_name: "Source Image",
  },
  {
    semantic_role: "hires_fix", node_id: "6", input_name: "use_hires",
    kind: "node_input", data_type: "BOOLEAN",
    enum_options: null, minimum: null, maximum: null, step: null,
    required: false, multiline: false, control_kind: "boolean", display_name: "Hires Fix",
  },
];

function _cloneEntries() {
  return CANDIDATE_ENTRIES.map((e) => ({ ...e }));
}

/** Falsy-safe defaults applied to seeded mapping entries (0/false/"" kept). */
function _defaultEntryValues() {
  return {
    sampler: "euler",
    scheduler: "normal",
    seed: 42,
    steps: 28,
    cfg: 7,
    positive_prompt: "",
    negative_prompt: "",
    model: "",
    width: 1024,
    height: 1024,
    denoise: 1,
    source_image: "",
    hires_fix: false,
  };
}

function _mappingEntriesWithDefaults() {
  const defaults = _defaultEntryValues();
  return _cloneEntries().map((e) => {
    const role = e.semantic_role || e.input_name;
    return { ...e, value: defaults[role] };
  });
}

// ── Enrichment ────────────────────────────────────────────────────────────

function _versionState(v) {
  const runnable = !!(v.mapping_id && v.output_node_id);
  return {
    status: runnable ? "ready" : "incomplete",
    reasons: runnable ? [] : ["missing mapping"],
    runnable,
  };
}

function _workflowSummary(state, w) {
  const versions = [...state.versions.values()].filter(
    (v) => v.workflow_id === w.workflow_id
  );
  const latest = w.latest_version_id ? state.versions.get(w.latest_version_id) : null;
  const defaultPreset = w.default_preset_id ? state.presets.get(w.default_preset_id) : null;
  return {
    ...w,
    version_count: versions.length,
    latest_version_id: w.latest_version_id,
    latest_version_number: latest ? latest.version_number : null,
    latest_version_state: latest
      ? _versionState(latest)
      : { status: "incomplete", reasons: ["no versions yet"], runnable: false },
    default_preset_name: defaultPreset ? defaultPreset.name : null,
  };
}

function _versionEnriched(state, v) {
  const mapping = state.mappings.get(v.workflow_version_id) || null;
  const presets = [...state.presets.values()].filter(
    (p) => p.workflow_version_id === v.workflow_version_id
  );
  return {
    ...v,
    state: _versionState(v),
    mapping_id: v.mapping_id || null,
    mapping: mapping
      ? {
          mapping_id: mapping.mapping_id,
          workflow_version_id: mapping.workflow_version_id,
          output_node_id: mapping.output_node_id,
          entries: mapping.entries,
        }
      : null,
    preset_count: presets.length,
    dependency_metadata: v.dependency_metadata || {
      model_stack: [],
      node_classes: [],
    },
  };
}

function _presetState(state, p, version) {
  if (!version) {
    return { status: "incomplete", reasons: ["version not found"], runnable: false };
  }
  const mapping = state.mappings.get(version.workflow_version_id);
  if (!mapping) {
    return { status: "incomplete", reasons: ["missing mapping"], runnable: false };
  }
  const reasons = [];
  const values = p.values || {};
  for (const e of mapping.entries || []) {
    if (!e.required) continue;
    const role = e.semantic_role || e.input_name;
    const val = values[role];
    if (val === undefined || val === null || val === "") {
      reasons.push(`missing value for required control '${role}'`);
    } else if (
      e.control_kind === "enum" &&
      Array.isArray(e.enum_options) &&
      !e.enum_options.includes(val)
    ) {
      reasons.push(
        `invalid value for '${role}': '${val}' is not one of ${e.enum_options.join(", ")}`
      );
    }
  }
  if (!_versionState(version).runnable) reasons.push("version state not runnable");
  const runnable = reasons.length === 0;
  return { status: runnable ? "ready" : "incomplete", reasons, runnable };
}

function _presetEnriched(state, p, wf) {
  const version = state.versions.get(p.workflow_version_id) || null;
  return {
    ...p,
    is_default: !!(wf && wf.default_preset_id === p.preset_id),
    state: _presetState(state, p, version),
  };
}

// ── installWorkflowsMock ─────────────────────────────────────────────────

export async function installWorkflowsMock(page, seed) {
  const state = {
    workflows: new Map(), // workflow_id → workflow record
    versions: new Map(),  // workflow_version_id → version record
    mappings: new Map(),  // workflow_version_id → mapping record
    presets: new Map(),   // preset_id → preset record
    calls: [],            // { method, path, body }
    unhandledWorkflowCalls: [], // { method, path } — workflow paths with no handler
  };

  // ── Seed helpers ──────────────────────────────────────────────────────

  function _nextVersionNumber(wfId) {
    let max = 0;
    for (const v of state.versions.values()) {
      if (v.workflow_id === wfId && (v.version_number || 0) > max) {
        max = v.version_number;
      }
    }
    return max + 1;
  }

  function seedWorkflow(overrides = {}) {
    const id = overrides.workflow_id || _makeId("wf_");
    const now = _now();
    const wf = {
      workflow_id: id,
      name: overrides.name || "Untitled workflow",
      description: overrides.description || "",
      folder: overrides.folder || "",
      tags: overrides.tags || [],
      favorite: !!overrides.favorite,
      source_url: overrides.source_url || "",
      source_author: overrides.source_author || "",
      compatible_models: overrides.compatible_models || [],
      created_at: now,
      updated_at: now,
      latest_version_id: "",
      default_preset_id: "",
    };
    state.workflows.set(id, wf);
    return wf;
  }

  function seedVersion(wfId, overrides = {}) {
    const wf = state.workflows.get(wfId);
    if (!wf) throw new Error("seedVersion: unknown workflow " + wfId);
    const num =
      overrides.version_number != null
        ? overrides.version_number
        : _nextVersionNumber(wfId);
    const vid = _makeId("ver_");
    const v = {
      workflow_version_id: vid,
      workflow_id: wfId,
      version_number: num,
      graph_json: overrides.graph_json || { nodes: [] },
      api_prompt_json: overrides.api_prompt_json || {},
      graph_hash: overrides.graph_hash || _makeId("h").slice(0, 10),
      created_at: overrides.created_at || _now(),
      updated_at: _now(),
      mapping_id: null,
      output_node_id: null,
      dependency_metadata: overrides.dependency_metadata || {
        model_stack: [],
        node_classes: [],
      },
    };
    state.versions.set(vid, v);
    if (overrides.mapping === true) {
      const m = {
        mapping_id: _makeId("map_"),
        workflow_version_id: vid,
        output_node_id: overrides.output_node_id || "6",
        entries: _mappingEntriesWithDefaults(),
        created_at: _now(),
        updated_at: _now(),
        immutable: true,
      };
      state.mappings.set(vid, m);
      v.mapping_id = m.mapping_id;
      v.output_node_id = m.output_node_id;
    }
    wf.latest_version_id = vid;
    wf.updated_at = _now();
    return v;
  }

  function seedPreset(versionId, overrides = {}) {
    const v = state.versions.get(versionId);
    if (!v) throw new Error("seedPreset: unknown version " + versionId);
    const pid = _makeId("preset_");
    const p = {
      preset_id: pid,
      workflow_version_id: versionId,
      name: overrides.name || "Untitled preset",
      description: overrides.description || "",
      tags: overrides.tags || [],
      favorite: !!overrides.favorite,
      values: overrides.values || {},
      model_choices: overrides.model_choices || {},
      lora_values: overrides.lora_values || {},
      recommended_values: overrides.recommended_values || {},
      exposed_controls: overrides.exposed_controls || [],
      created_at: _now(),
      updated_at: _now(),
    };
    state.presets.set(pid, p);
    return p;
  }

  function seedDefaultDataset() {
    // Portrait Pro: versions 1 + 2, both mapped. Version 2 is the latest and
    // carries the runnable current preset; v1 remains historical fixture data.
    const pp = seedWorkflow({
      name: "Portrait Pro",
      folder: "Portraits",
      tags: ["portrait"],
      source_author: "Modal Team",
    });
    const ppV1 = seedVersion(pp.workflow_id, { version_number: 1, mapping: true });
    const portraitValues = {
      sampler: "euler",
      scheduler: "normal",
      seed: 42,
      steps: 28,
      cfg: 7,
      positive_prompt: "A portrait of a woman",
      negative_prompt: "blurry",
      model: "test-model.safetensors",
      width: 1024,
      height: 1024,
      denoise: 1,
      source_image: "",
      hires_fix: false,
    };
    seedPreset(ppV1.workflow_version_id, {
      name: "Portrait Default",
      values: { ...portraitValues },
    });
    const ppV2 = seedVersion(pp.workflow_id, {
      version_number: 2,
      mapping: true,
      dependency_metadata: {
        model_stack: ["sd_xl_base_1.0.safetensors"],
        node_classes: ["KSampler", "CLIPTextEncode"],
      },
    });
    // Keep v1 as historical fixture data while ensuring the current version
    // is runnable in the Shelf.
    seedPreset(ppV2.workflow_version_id, {
      name: "Portrait Current",
      values: { ...portraitValues },
    });

    // Abstract Test: version 1 UNMAPPED → state incomplete, run disabled.
    const at = seedWorkflow({
      name: "Abstract Test",
      folder: "Abstract",
      tags: ["experiment"],
    });
    seedVersion(at.workflow_id, { version_number: 1, mapping: false });
  }

  // Seed the default dataset. An explicit `seed` option is accepted for
  // symmetry with installStudioMockApi(page, options) but unused for now.
  seedDefaultDataset();

  // ── Query helpers (spec-facing) ───────────────────────────────────────

  function getWorkflow(name) {
    return [...state.workflows.values()].find((w) => w.name === name) || null;
  }

  function getVersions(wfId) {
    return [...state.versions.values()].filter((v) => v.workflow_id === wfId);
  }

  function getPresets(versionId) {
    return [...state.presets.values()].filter(
      (p) => p.workflow_version_id === versionId
    );
  }

  function findCall(method, pathPart) {
    return state.calls.find((c) => c.method === method && c.path.includes(pathPart)) || null;
  }

  function callsFor(method, pathPart) {
    return state.calls.filter((c) => c.method === method && c.path.includes(pathPart));
  }

  function reset() {
    state.workflows.clear();
    state.versions.clear();
    state.mappings.clear();
    state.presets.clear();
    state.calls.length = 0;
    state.unhandledWorkflowCalls.length = 0;
    seedDefaultDataset();
  }

  function assertNoUnhandledWorkflowCalls() {
    if (state.unhandledWorkflowCalls.length > 0) {
      const lines = state.unhandledWorkflowCalls.map((u) => `  ${u.method} ${u.path}`);
      throw new Error(
        "Unhandled workflow mock calls (" +
          state.unhandledWorkflowCalls.length +
          "):\n" +
          lines.join("\n")
      );
    }
  }

  // ── Route handlers ──────────────────────────────────────────────────────

  function listWorkflows(route, url, body, params) {
    const search = url.searchParams.get("search") || "";
    const tag = url.searchParams.get("tag") || "";
    const folder = url.searchParams.get("folder") || "";
    const favoriteOnly = url.searchParams.get("favorite") === "1";
    let list = [...state.workflows.values()];
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((w) =>
        [w.name, w.description, (w.tags || []).join(" ")]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(q)
      );
    }
    if (tag) list = list.filter((w) => (w.tags || []).includes(tag));
    if (folder) list = list.filter((w) => String(w.folder || "").startsWith(folder));
    if (favoriteOnly) list = list.filter((w) => w.favorite);
    return _json({ status: "ok", workflows: list.map((w) => _workflowSummary(state, w)) });
  }

  function createWorkflow(route, url, body) {
    const wf = seedWorkflow({
      name: (body && body.name) || "Untitled workflow",
      description: (body && body.description) || "",
      folder: (body && body.folder) || "",
    });
    return _json({ status: "ok", workflow: _workflowSummary(state, wf) });
  }

  function importWorkflow(route, url, body) {
    const wf = seedWorkflow({
      name: (body && body.name) || "Imported workflow",
    });
    const v = seedVersion(wf.workflow_id, {
      version_number: 1,
      mapping: false,
      graph_json: body ? body.graph_json : null,
      api_prompt_json: body ? body.api_prompt_json : null,
    });
    return _json({
      status: "ok",
      workflow: _workflowSummary(state, wf),
      version: _versionEnriched(state, v),
    });
  }

  function listFolders(route, url, body, params) {
    const folders = [
      ...new Set(
        [...state.workflows.values()]
          .map((w) => w.folder)
          .filter(Boolean)
      ),
    ].sort();
    return _json({ status: "ok", folders });
  }

  function listTags(route, url, body, params) {
    const tags = [
      ...new Set(
        [...state.workflows.values()].flatMap((w) => w.tags || [])
      ),
    ].sort();
    return _json({ status: "ok", tags });
  }

  // NOTE: named getWorkflowDetail (not getWorkflow) so the route handler
  // cannot shadow the spec-facing getWorkflow(name) query helper below —
  // duplicate function declarations in this closure would otherwise make
  // wfMock.getWorkflow("...") invoke the handler with params undefined.
  function getWorkflowDetail(route, url, body, params) {
    const w = state.workflows.get(params.id);
    if (!w) return _error("Workflow not found", 404);
    return _json({ status: "ok", workflow: _workflowSummary(state, w) });
  }

  function updateWorkflow(route, url, body, params) {
    const w = state.workflows.get(params.id);
    if (!w) return _error("Workflow not found", 404);
    if (body) {
      if (body.name !== undefined) w.name = String(body.name);
      if (body.description !== undefined) w.description = String(body.description);
      if (body.folder !== undefined) w.folder = String(body.folder);
      if (body.tags !== undefined) {
        w.tags = Array.isArray(body.tags) ? body.tags.map(String) : [];
      }
      if (body.favorite !== undefined) w.favorite = !!body.favorite;
      if (body.source_url !== undefined) w.source_url = String(body.source_url);
      if (body.source_author !== undefined) w.source_author = String(body.source_author);
    }
    w.updated_at = _now();
    return _json({ status: "ok", workflow: _workflowSummary(state, w) });
  }

  function setDefaultPreset(route, url, body, params) {
    const w = state.workflows.get(params.id);
    if (!w) return _error("Workflow not found", 404);
    const pid = body && body.preset_id;
    if (!pid || !state.presets.has(pid)) return _error("Preset not found", 404);
    w.default_preset_id = pid;
    w.updated_at = _now();
    return _json({ status: "ok", workflow: _workflowSummary(state, w) });
  }

  function clearDefaultPreset(route, url, body, params) {
    const w = state.workflows.get(params.id);
    if (!w) return _error("Workflow not found", 404);
    w.default_preset_id = "";
    w.updated_at = _now();
    return _json({ status: "ok", workflow: _workflowSummary(state, w) });
  }

  function getRunContext(route, url, body, params) {
    const w = state.workflows.get(params.id);
    if (!w) return _error("Workflow not found", 404);
    const vid = url.searchParams.get("version_id") || w.latest_version_id || "";
    const version = vid ? state.versions.get(vid) : null;
    const mapping = version ? state.mappings.get(version.workflow_version_id) || null : null;
    const defaultPreset = w.default_preset_id ? state.presets.get(w.default_preset_id) : null;
    return _json({
      status: "ok",
      workflow: _workflowSummary(state, w),
      version: version ? _versionEnriched(state, version) : null,
      mapping: mapping
        ? {
            mapping_id: mapping.mapping_id,
            workflow_version_id: mapping.workflow_version_id,
            output_node_id: mapping.output_node_id,
            entries: mapping.entries,
          }
        : null,
      default_preset: defaultPreset ? _presetEnriched(state, defaultPreset, w) : null,
      state: version ? _versionState(version) : null,
      control_schema: mapping ? mapping.entries : [],
    });
  }

  function listWorkflowVersions(route, url, body, params) {
    const w = state.workflows.get(params.id);
    if (!w) return _error("Workflow not found", 404);
    const versions = [...state.versions.values()].filter(
      (v) => v.workflow_id === params.id
    );
    return _json({ status: "ok", versions: versions.map((v) => _versionEnriched(state, v)) });
  }

  function captureVersion(route, url, body, params) {
    const w = state.workflows.get(params.id);
    if (!w) return _error("Workflow not found", 404);
    const graphJson = body ? body.graph_json : undefined;
    const key = graphJson !== undefined ? JSON.stringify(graphJson) : null;
    if (key !== null) {
      for (const v of state.versions.values()) {
        if (v.workflow_id === params.id && JSON.stringify(v.graph_json) === key) {
          return _json({ status: "ok", version: _versionEnriched(state, v) });
        }
      }
    }
    const v = seedVersion(params.id, {
      graph_json: graphJson || null,
      api_prompt_json: body ? body.api_prompt_json : null,
    });
    return _json({ status: "ok", version: _versionEnriched(state, v) });
  }

  function getWorkflowVersion(route, url, body, params) {
    const v = state.versions.get(params.vid);
    if (!v) return _error("Version not found", 404);
    return _json({ status: "ok", version: _versionEnriched(state, v) });
  }

  function getVersionDependencies(route, url, body, params) {
    const v = state.versions.get(params.vid);
    if (!v) return _error("Version not found", 404);
    const meta = v.dependency_metadata || { model_stack: [], node_classes: [] };
    const stack = Array.isArray(meta.model_stack) ? meta.model_stack : [];
    const models = stack.map((filename) => ({
      key: "model|" + filename,
      role: "model",
      filename: String(filename),
      state: "unknown",
      source_urls: [],
    }));
    return _json({
      status: "ok",
      version_id: v.workflow_version_id,
      models,
      custom_nodes: [],
      summary: {
        installed: 0,
        missing: models.length,
        wrong_version: 0,
        unknown: 0,
        attention: models.length,
        ready: models.length === 0,
      },
    });
  }

  function getVersionState(route, url, body, params) {
    const v = state.versions.get(params.vid);
    if (!v) return _error("Version not found", 404);
    return _json({ status: "ok", state: _versionState(v) });
  }

  function getMapping(route, url, body, params) {
    const v = state.versions.get(params.vid);
    if (!v) return _error("Version not found", 404);
    const m = state.mappings.get(params.vid);
    if (!m) return _json({ status: "ok", mapping: null });
    return _json({
      status: "ok",
      mapping: {
        mapping_id: m.mapping_id,
        workflow_version_id: m.workflow_version_id,
        output_node_id: m.output_node_id,
        entries: m.entries,
      },
    });
  }

  function createMapping(route, url, body, params) {
    const v = state.versions.get(params.vid);
    if (!v) return _error("Version not found", 404);
    if (state.mappings.has(params.vid)) {
      return _json(
        {
          status: "error",
          message:
            "This version already has an immutable mapping. Create a new version to change the mapping.",
          _httpStatus: 409,
        },
        409
      );
    }
    // The real mapping POST contract carries entries as a dict keyed by
    // semantic role (the server normalizes and reads it back as a list).
    // Normalize here so the mocked read-back matches the server shape and
    // every list-shaped consumer (badges, preset editor, copy) keeps
    // working. List payloads (legacy editor) pass through untouched.
    const rawEntries = body && body.entries;
    const entries = Array.isArray(rawEntries)
      ? rawEntries
      : Object.entries(rawEntries && typeof rawEntries === "object" ? rawEntries : {}).map(
          ([role, e]) => ({ semantic_role: role, ...(e && typeof e === "object" ? e : {}) })
        );
    const m = {
      mapping_id: _makeId("map_"),
      workflow_version_id: params.vid,
      output_node_id: (body && body.output_node_id) || null,
      entries,
      created_at: _now(),
      updated_at: _now(),
      immutable: true,
    };
    state.mappings.set(params.vid, m);
    v.mapping_id = m.mapping_id;
    v.output_node_id = m.output_node_id;
    v.updated_at = _now();
    return _json({
      status: "ok",
      mapping: {
        mapping_id: m.mapping_id,
        workflow_version_id: m.workflow_version_id,
        output_node_id: m.output_node_id,
        entries: m.entries,
      },
    });
  }

  function getMappingCandidates(route, url, body, params) {
    return _json({
      status: "ok",
      candidates: { entries: _cloneEntries(), output_node_id: "6" },
    });
  }

  function createMappingRevision(route, url, body, params) {
    const oldV = state.versions.get(params.vid);
    if (!oldV) return _error("Version not found", 404);
    const wf = state.workflows.get(oldV.workflow_id);
    const vid = _makeId("ver_");
    const num = _nextVersionNumber(oldV.workflow_id);
    const v = {
      workflow_version_id: vid,
      workflow_id: oldV.workflow_id,
      version_number: num,
      graph_json: oldV.graph_json,
      api_prompt_json: oldV.api_prompt_json,
      graph_hash: oldV.graph_hash,
      created_at: _now(),
      updated_at: _now(),
      mapping_id: null,
      output_node_id: null,
      dependency_metadata:
        oldV.dependency_metadata || { model_stack: [], node_classes: [] },
    };
    const m = {
      mapping_id: _makeId("map_"),
      workflow_version_id: vid,
      output_node_id:
        (body && body.output_node_id) || oldV.output_node_id || null,
      entries: body && Array.isArray(body.entries) ? body.entries : [],
      created_at: _now(),
      updated_at: _now(),
      immutable: true,
    };
    state.versions.set(vid, v);
    state.mappings.set(vid, m);
    v.mapping_id = m.mapping_id;
    v.output_node_id = m.output_node_id;
    if (wf) {
      wf.latest_version_id = vid;
      wf.updated_at = _now();
    }
    return _json({ status: "ok", version: _versionEnriched(state, v) });
  }

  function listVersionPresets(route, url, body, params) {
    const v = state.versions.get(params.vid);
    if (!v) return _error("Version not found", 404);
    const wf = state.workflows.get(v.workflow_id);
    const presets = [...state.presets.values()].filter(
      (p) => p.workflow_version_id === params.vid
    );
    return _json({
      status: "ok",
      presets: presets.map((p) => _presetEnriched(state, p, wf)),
    });
  }

  function createVersionPreset(route, url, body, params) {
    const v = state.versions.get(params.vid);
    if (!v) return _error("Version not found", 404);
    const wf = state.workflows.get(v.workflow_id);
    const p = seedPreset(params.vid, {
      name: (body && body.name) || "Untitled preset",
      description: (body && body.description) || "",
      tags: body && Array.isArray(body.tags) ? body.tags : [],
      favorite: !!(body && body.favorite),
      // Values are stored verbatim — 0, 0.0, false and "" are preserved.
      values: body && typeof body.values === "object" && body.values !== null ? body.values : {},
      model_choices:
        body && typeof body.model_choices === "object" && body.model_choices !== null
          ? body.model_choices
          : {},
      lora_values: body && body.lora_values ? body.lora_values : {},
      recommended_values:
        body && typeof body.recommended_values === "object" && body.recommended_values !== null
          ? body.recommended_values
          : {},
      exposed_controls: body && Array.isArray(body.exposed_controls) ? body.exposed_controls : [],
    });
    return _json({ status: "ok", preset: _presetEnriched(state, p, wf) });
  }

  // ── Legacy absorption bridge (abs-2) ────────────────────────────────
  // Mirrors the verified abs-1 server contract
  // (studio_domain/legacy_adapters.py LEGACY_ROLE_MAP): positive_prompt→
  // prompt, steps→step_count, cfg→cfg_scale, guidance→cfg_scale,
  // model→model_unet, unet→model_unet; unknown keys pass through verbatim.
  // The mock applies that exact map so specs can assert the canonical
  // persistence the real from-legacy route guarantees.
  const LEGACY_ROLE_MAP = {
    positive_prompt: "prompt",
    steps: "step_count",
    cfg: "cfg_scale",
    guidance: "cfg_scale",
    model: "model_unet",
    unet: "model_unet",
  };

  function _translateLegacyKeys(container) {
    const out = {};
    if (container && typeof container === "object") {
      for (const [k, v] of Object.entries(container)) {
        out[LEGACY_ROLE_MAP[k] || k] = v;
      }
    }
    return out;
  }

  function createPresetFromLegacy(route, url, body, params) {
    const v = state.versions.get(params.vid);
    if (!v) return _error("Version not found", 404);
    const b = body || {};
    const name = (typeof b.name === "string" && b.name.trim())
      || (typeof b.label === "string" && b.label.trim())
      || "";
    if (!name) return _error("preset name is required", 400);
    const wf = state.workflows.get(v.workflow_id);
    const p = seedPreset(params.vid, {
      name,
      description: typeof b.description === "string" ? b.description : "",
      tags: Array.isArray(b.tags) ? b.tags : [],
      favorite: !!b.favorite,
      // Legacy roles translated to canonical keys (unknowns verbatim).
      values: _translateLegacyKeys(b.values),
      model_choices: _translateLegacyKeys(b.model_choices),
      lora_values: b.lora_values || {},
      recommended_values: b.recommended_values || {},
      exposed_controls: Array.isArray(b.exposed_controls) ? b.exposed_controls : [],
    });
    return _json({ status: "ok", preset: _presetEnriched(state, p, wf) });
  }

  function getWorkflowPreset(route, url, body, params) {
    const p = state.presets.get(params.pid);
    if (!p) return _error("Preset not found", 404);
    const v = state.versions.get(p.workflow_version_id);
    const wf = v ? state.workflows.get(v.workflow_id) : null;
    return _json({ status: "ok", preset: _presetEnriched(state, p, wf) });
  }

  function updateWorkflowPreset(route, url, body, params) {
    const p = state.presets.get(params.pid);
    if (!p) return _error("Preset not found", 404);
    if (body) {
      if (body.name !== undefined) p.name = String(body.name);
      if (body.description !== undefined) p.description = String(body.description);
      if (body.tags !== undefined) p.tags = Array.isArray(body.tags) ? body.tags : [];
      if (body.favorite !== undefined) p.favorite = !!body.favorite;
      if (body.values !== undefined && typeof body.values === "object") p.values = body.values;
      if (body.model_choices !== undefined) p.model_choices = body.model_choices;
      if (body.lora_values !== undefined) p.lora_values = body.lora_values;
      if (body.recommended_values !== undefined) p.recommended_values = body.recommended_values;
      if (body.exposed_controls !== undefined) p.exposed_controls = body.exposed_controls;
    }
    p.updated_at = _now();
    const v = state.versions.get(p.workflow_version_id);
    const wf = v ? state.workflows.get(v.workflow_id) : null;
    return _json({ status: "ok", preset: _presetEnriched(state, p, wf) });
  }

  function deleteWorkflowPreset(route, url, body, params) {
    const p = state.presets.get(params.pid);
    if (!p) return _error("Preset not found", 404);
    state.presets.delete(params.pid);
    return _json({ status: "ok" });
  }

  function duplicatePreset(route, url, body, params) {
    const p = state.presets.get(params.pid);
    if (!p) return _error("Preset not found", 404);
    const copy = {
      ...p,
      preset_id: _makeId("preset_"),
      name: (p.name || "Untitled preset") + " (Copy)",
      created_at: _now(),
      updated_at: _now(),
    };
    state.presets.set(copy.preset_id, copy);
    const v = state.versions.get(copy.workflow_version_id);
    const wf = v ? state.workflows.get(v.workflow_id) : null;
    return _json({ status: "ok", preset: _presetEnriched(state, copy, wf) });
  }

  function copyPresetToVersion(route, url, body, params) {
    const src = state.presets.get(params.pid);
    if (!src) return _error("Preset not found", 404);
    const targetVid = body && body.target_version_id;
    const target = state.versions.get(targetVid);
    if (!target) return _error("Version not found", 404);
    const targetMapping = state.mappings.get(targetVid);
    const targetEntries = (targetMapping && targetMapping.entries) || [];
    const dropped = Object.keys(src.values || {}).filter(
      (role) => !targetEntries.some((e) => (e.semantic_role || e.input_name) === role)
    );
    const copy = {
      ...src,
      preset_id: _makeId("preset_"),
      workflow_version_id: targetVid,
      created_at: _now(),
      updated_at: _now(),
    };
    state.presets.set(copy.preset_id, copy);
    const wf = state.workflows.get(target.workflow_id);
    return _json({
      status: "ok",
      result: {
        preset: _presetEnriched(state, copy, wf),
        dropped_controls: dropped,
        state: _presetState(state, copy, target),
      },
    });
  }

  function bulkCopyPresets(route, url, body, params) {
    const source = state.versions.get(params.vid);
    if (!source) return _error("Version not found", 404);
    const wf = state.workflows.get(source.workflow_id);
    const targetVid = wf && wf.latest_version_id;
    const target = targetVid ? state.versions.get(targetVid) : null;
    if (!target) return _error("Version not found", 404);
    const ids = body && Array.isArray(body.preset_ids) ? body.preset_ids : [];
    const targetMapping = state.mappings.get(targetVid);
    const targetEntries = (targetMapping && targetMapping.entries) || [];
    const results = ids
      .map((pid) => state.presets.get(pid))
      .filter(Boolean)
      .map((src) => {
        const dropped = Object.keys(src.values || {}).filter(
          (role) => !targetEntries.some((e) => (e.semantic_role || e.input_name) === role)
        );
        const copy = {
          ...src,
          preset_id: _makeId("preset_"),
          workflow_version_id: targetVid,
          created_at: _now(),
          updated_at: _now(),
        };
        state.presets.set(copy.preset_id, copy);
        return {
          preset: _presetEnriched(state, copy, wf),
          dropped_controls: dropped,
          state: _presetState(state, copy, target),
          source_preset_id: src.preset_id,
        };
      });
    return _json({ status: "ok", results });
  }

  // ── Route table ────────────────────────────────────────────────────────
  // Static paths before param paths; version/preset scoped paths before the
  // bare /workflows/:id catch-alls (regexes are anchored, order is still kept
  // explicit for readability).

  const routeEntries = [
    ["GET", "/comfymodal/studio/workflows/folders", listFolders],
    ["GET", "/comfymodal/studio/workflows/tags", listTags],
    ["POST", "/comfymodal/studio/workflows/import", importWorkflow],

    ["GET", "/comfymodal/studio/workflows/versions/:vid/state", getVersionState],
    ["GET", "/comfymodal/studio/workflows/versions/:vid/mapping/candidates", getMappingCandidates],
    ["POST", "/comfymodal/studio/workflows/versions/:vid/mapping/revision", createMappingRevision],
    ["POST", "/comfymodal/studio/workflows/versions/:vid/mapping", createMapping],
    ["GET", "/comfymodal/studio/workflows/versions/:vid/mapping", getMapping],
    ["GET", "/comfymodal/studio/workflows/versions/:vid/dependencies", getVersionDependencies],
    ["POST", "/comfymodal/studio/workflows/versions/:vid/presets/copy-bulk", bulkCopyPresets],
    ["POST", "/comfymodal/studio/workflows/versions/:vid/presets/from-legacy", createPresetFromLegacy],
    ["GET", "/comfymodal/studio/workflows/versions/:vid/presets", listVersionPresets],
    ["POST", "/comfymodal/studio/workflows/versions/:vid/presets", createVersionPreset],
    ["GET", "/comfymodal/studio/workflows/versions/:vid", getWorkflowVersion],

    ["POST", "/comfymodal/studio/workflows/presets/:pid/duplicate", duplicatePreset],
    ["POST", "/comfymodal/studio/workflows/presets/:pid/copy-to-version", copyPresetToVersion],
    ["GET", "/comfymodal/studio/workflows/presets/:pid", getWorkflowPreset],
    ["PATCH", "/comfymodal/studio/workflows/presets/:pid", updateWorkflowPreset],
    ["DELETE", "/comfymodal/studio/workflows/presets/:pid", deleteWorkflowPreset],

    ["GET", "/comfymodal/studio/workflows", listWorkflows],
    ["POST", "/comfymodal/studio/workflows", createWorkflow],
    ["POST", "/comfymodal/studio/workflows/:id/default-preset", setDefaultPreset],
    ["DELETE", "/comfymodal/studio/workflows/:id/default-preset", clearDefaultPreset],
    ["GET", "/comfymodal/studio/workflows/:id/run-context", getRunContext],
    ["GET", "/comfymodal/studio/workflows/:id/versions", listWorkflowVersions],
    ["POST", "/comfymodal/studio/workflows/:id/versions", captureVersion],
    ["PATCH", "/comfymodal/studio/workflows/:id", updateWorkflow],
    ["GET", "/comfymodal/studio/workflows/:id", getWorkflowDetail],
  ];

  const compiledRoutes = routeEntries.map(([method, pattern, handler]) => {
    const { regex, paramNames } = _compilePattern(pattern);
    return { method, regex, paramNames, handler };
  });

  // ── Install page.route BEFORE navigation ────────────────────────────────
  // Regex covers both the bare /comfymodal/studio/workflows path (list/create)
  // and every /comfymodal/studio/workflows/** sub-path. Registered AFTER the
  // shared mock so it takes precedence for workflow requests.

  await page.route(/\/comfymodal\/studio\/workflows/, async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const pathname = url.pathname;

    let body;
    if (["POST", "PATCH", "PUT", "DELETE"].includes(method)) {
      const raw = request.postData();
      if (raw) {
        try {
          body = JSON.parse(raw);
        } catch {
          body = undefined;
        }
      }
    }

    for (const entry of compiledRoutes) {
      if (entry.method !== method) continue;
      const match = pathname.match(entry.regex);
      if (!match) continue;
      const params = {};
      for (let i = 0; i < entry.paramNames.length; i++) {
        params[entry.paramNames[i]] = decodeURIComponent(match[i + 1]);
      }
      state.calls.push({ method, path: pathname, body });
      try {
        const result = await entry.handler(route, url, body, params);
        return route.fulfill({
          status: result.status,
          contentType: result.contentType,
          body: result.body,
        });
      } catch (err) {
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            status: "error",
            message: "Workflow mock handler error: " + err.message,
            _httpStatus: 500,
          }),
        });
      }
    }

    // No handler matched → record for assertNoUnhandledWorkflowCalls.
    state.unhandledWorkflowCalls.push({ method, path: pathname });
    state.calls.push({ method, path: pathname, body });
    return route.fulfill({
      status: 599,
      contentType: "application/json",
      body: JSON.stringify({
        status: "error",
        message: "unhandled workflow mock endpoint",
        _httpStatus: 599,
      }),
    });
  });

  return {
    state,
    reset,
    seedWorkflow,
    seedVersion,
    seedPreset,
    getWorkflow,
    getVersions,
    getPresets,
    findCall,
    callsFor,
    assertNoUnhandledWorkflowCalls,
  };
}
