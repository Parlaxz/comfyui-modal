// Modal Studio — Fake Backend HTTP Server (Playwright harness)
//
// Standalone node:http server (no external dependencies) that exposes the
// deterministic fake backend (fake-backend.mjs) plus the static harness
// files.  It also serves the real Studio frontend modules from web/ under
// /extensions/comfymodal-modal/ so the harness page can mount the actual
// Studio UI against the fake REST + event-bus.
//
// Run:   node tests/browser/fake/fake-server.mjs
// Port:  env STUDIO_FAKE_PORT || 8377
//
// Session mechanics: the harness page sets cookie `comfymodal_fake_session`
// (see harness-bootstrap.js) before mounting; every same-origin request the
// app makes automatically carries it.  Test-control endpoints accept an
// explicit `sessionId`/`session` for requests made without the cookie.

import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import * as engine from "./fake-backend.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FAKE_DIR = __dirname;
const HARNESS_DIR = path.join(FAKE_DIR, "harness");
const WEB_DIR = path.resolve(FAKE_DIR, "../../../web");
const DEFAULT_SESSION = "sess_default";

const MIME = {
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".ttf": "font/ttf",
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
}

function _json(res, data, status = 200) {
  // Drop the internal _httpStatus marker so error envelopes stay exactly
  // {"status","message"} — it is a transport detail, not part of the payload.
  const body = JSON.stringify(data, (key, value) => (key === "_httpStatus" ? undefined : value));
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function _error(res, message, status = 404) {
  _json(res, { status: "error", message }, status);
}

function _buffer(res, bytes, contentType) {
  res.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": bytes.length,
    "Cache-Control": "no-store",
  });
  res.end(bytes);
}

function _file(res, bytes, contentType) {
  res.writeHead(200, { "Content-Type": contentType, "Cache-Control": "no-store" });
  res.end(bytes);
}

// ── Request helpers ─────────────────────────────────────────────────────

async function _readBody(req) {
  const chunks = [];
  return new Promise((resolve, reject) => {
    req.on("data", (c) => {
      chunks.push(c);
      if (chunks.length > 50) req.destroy(); // 50 chunks is plenty for JSON
    });
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      if (!raw.trim()) return resolve(null);
      try {
        resolve(JSON.parse(raw));
      } catch {
        resolve({ _raw: raw });
      }
    });
    req.on("error", reject);
  });
}

function _getCookie(req, name) {
  const header = req.headers.cookie || "";
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === name) {
      return decodeURIComponent(part.slice(eq + 1).trim());
    }
  }
  return null;
}

function _sessionIdFromRequest(req, url, body) {
  // 1. Explicit session in body (test-control POSTs)
  if (body && (body.sessionId || body.session)) return body.sessionId || body.session;
  // 2. Explicit ?session= query param
  const qs = url.searchParams.get("session");
  if (qs) return qs;
  // 3. Cookie set by the harness bootstrap
  const cookie = _getCookie(req, "comfymodal_fake_session");
  if (cookie) return cookie;
  return DEFAULT_SESSION;
}

function _sessionOrError(res, id, fn) {
  try {
    return fn(id);
  } catch (err) {
    if (err && err.code === "UNKNOWN_SESSION") {
      _error(res, err.message, 404);
      return null;
    }
    throw err;
  }
}

// ── Deterministic Workflows + Model Library state (session-scoped) ───────

const STUDIO_STATE = new Map(); // sessionId → { models, customNodes, coreClasses, workflow, version }

function _isoNow() {
  return new Date().toISOString();
}

const FAKE_WF_INCOMPLETE_STATE = {
  status: "incomplete",
  reasons: ["missing model 'krea_model.safetensors' (checkpoints)"],
  runnable: false,
};

function _fakeDependenciesPayload() {
  return {
    status: "ok",
    version_id: "wv_fake",
    models: [
      {
        key: "checkpoint|krea_model.safetensors",
        role: "checkpoint",
        filename: "krea_model.safetensors",
        state: "missing",
        model_id: "ml_krea",
        folder: "checkpoints",
        source_urls: ["https://huggingface.co/example/krea"],
      },
    ],
    custom_nodes: [
      {
        name: "SomeCustomClass",
        state: "installed",
        install_path: "/custom_nodes/ComfyUI-KJNodes",
        installed_commit: "abc1234",
        repository_url: "https://github.com/kijai/ComfyUI-KJNodes",
        classes: ["SomeCustomClass"],
      },
    ],
    summary: { installed: 1, missing: 1, wrong_version: 0, unknown: 0, attention: 1, ready: false },
  };
}

function _fakeVersion() {
  return {
    workflow_version_id: "wv_fake",
    workflow_id: "wf_fake",
    version_number: 1,
    created_at: _isoNow(),
    updated_at: _isoNow(),
    graph_hash: "abcdef0123",
    mapping_id: null,
    preset_count: 0,
    dependency_metadata: {
      model_stack: { checkpoint: ["krea_model.safetensors"] },
      node_classes: ["CheckpointLoaderSimple", "SomeCustomClass"],
    },
    compatible_models: ["krea_model.safetensors"],
    state: Object.assign({}, FAKE_WF_INCOMPLETE_STATE),
  };
}

function _fakeWorkflow() {
  return {
    workflow_id: "wf_fake",
    name: "Fake Workflow",
    description: "",
    folder: "",
    tags: [],
    favorite: false,
    latest_version_id: "wv_fake",
    latest_version_number: 1,
    latest_version_state: Object.assign({}, FAKE_WF_INCOMPLETE_STATE),
    source_url: "",
    source_author: "",
    default_preset_name: "",
    compatible_models: ["krea_model.safetensors"],
    updated_at: _isoNow(),
  };
}

const SEED_MODELS = [
  {
    model_id: "ml_krea",
    folder: "checkpoints",
    filename: "krea_model.safetensors",
    display_name: "Krea Model",
    model_type: "checkpoint",
    local_path: "/models/checkpoints/krea_model.safetensors",
    hash: "aaaa1111bbbb2222cccc3333dddd4444",
    size: 6.5e9,
    source_urls: ["https://huggingface.co/example/krea"],
    provider: "huggingface",
    revision: "main",
    installed: false,
    is_placeholder: false,
    notes: "",
    tags: ["krea"],
    discovered_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
  },
  {
    model_id: "ml_sd15_v2",
    folder: "checkpoints",
    filename: "sd15_v2.safetensors",
    display_name: "SD 1.5 Base",
    model_type: "checkpoint",
    local_path: "/models/checkpoints/sd15_v2.safetensors",
    hash: "bbbb2222cccc3333dddd4444eeee5555",
    size: 3.9e9,
    source_urls: [],
    provider: "",
    revision: "",
    installed: true,
    is_placeholder: false,
    notes: "",
    tags: ["sd15"],
    discovered_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
  },
  {
    model_id: "ml_vae",
    folder: "vae",
    filename: "vae-ft-mse.safetensors",
    display_name: "VAE",
    model_type: "vae",
    local_path: "/models/vae/vae-ft-mse.safetensors",
    hash: "cccc3333dddd4444eeee5555ffff6666",
    size: 3.35e8,
    source_urls: [],
    provider: "",
    revision: "",
    installed: true,
    is_placeholder: false,
    notes: "",
    tags: ["vae"],
    discovered_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
  },
];

const SEED_CUSTOM_NODES = [
  {
    name: "ComfyUI-KJNodes",
    install_path: "/custom_nodes/ComfyUI-KJNodes",
    repo_url: "https://github.com/kijai/ComfyUI-KJNodes",
    installed_commit: "abc1234",
    classes: ["SomeCustomClass"],
    updated_at: "2026-01-01T00:00:00.000Z",
  },
];

function _studioSeed(sid) {
  let s = STUDIO_STATE.get(sid);
  if (s) return s;
  s = {
    models: SEED_MODELS.map((m) => Object.assign({}, m)),
    customNodes: SEED_CUSTOM_NODES.map((n) => Object.assign({}, n)),
    coreClasses: ["CheckpointLoaderSimple"],
    workflow: _fakeWorkflow(),
    version: _fakeVersion(),
  };
  STUDIO_STATE.set(sid, s);
  return s;
}

// Mirror of the engine's listFakeWorkflows filter semantics (search/tag/
// folder/favorite) applied to the legacy wf_fake record so picker
// list/search filtering is consistent across both sources.
function _legacyMatchesPickerQuery(wf, q) {
  const search = String((q && q.search) || "").toLowerCase();
  if (search) {
    const hay = [wf.name, wf.description].filter(Boolean).join(" ").toLowerCase();
    if (hay.indexOf(search) === -1) return false;
  }
  const tag = String((q && q.tag) || "");
  if (tag && !((wf.tags || []).includes(tag))) return false;
  const folder = String((q && q.folder) || "");
  if (folder && !(String(wf.folder || "") === folder ||
    String(wf.folder || "").startsWith(folder + "/"))) return false;
  if (String((q && q.favorite) || "") === "1" && !wf.favorite) return false;
  return true;
}

// ── Workflow binding state (leaf 1.2.1 follow-up, session-scoped) ───────
// The engine seeds immutable mappings for mapped versions but exposes no
// binding-mutation surface. Bindings created here via POST .../mapping live
// in this server-local map (keyed by session + version) so the fake harness
// can exercise the exact-binding flow: candidates → create (409 when a
// mapping already exists) → read-back. Seeded engine mappings always win;
// local state only covers versions the engine reports as unmapped.
const LOCAL_BINDINGS = new Map(); // `${sid}::${vid}` → mapping record
let _localBindingSeq = 0;

function _bindingKey(sid, vid) {
  return `${sid}::${vid}`;
}

// Resolve a version across both stores: the legacy wf_fake record and the
// seeded engine dataset. Returns null when the version id is unknown.
function _resolveFakeVersion(sid, vid) {
  const s = _studioSeed(sid);
  if (vid === s.version.workflow_version_id) return { record: s.version, legacy: true };
  const r = engine.getFakeWorkflowVersion(sid, vid);
  if (r && r.status === "ok" && r.version) return { record: r.version, legacy: false };
  return null;
}

// Effective mapping for a version: local creation first, then the engine.
// (Engine mappings are immutable seeds; local state only exists where the
// engine reports no mapping.)
function _effectiveFakeMapping(sid, vid) {
  const local = LOCAL_BINDINGS.get(_bindingKey(sid, vid));
  if (local) return local;
  const r = engine.getFakeMapping(sid, vid);
  if (r && r.mapping) return r.mapping;
  return null;
}

// ── Static file serving ─────────────────────────────────────────────────

async function _serveFile(res, fullPath, fallbackContentType) {
  try {
    const bytes = await readFile(fullPath);
    const ext = path.extname(fullPath).toLowerCase();
    _file(res, bytes, MIME[ext] || fallbackContentType || "application/octet-stream");
  } catch {
    _error(res, `not found: ${path.basename(fullPath)}`, 404);
  }
}

function _resolveInside(dir, relative) {
  const target = path.resolve(dir, "." + relative);
  const normDir = path.resolve(dir);
  if (target !== normDir && !target.startsWith(normDir + path.sep)) return null;
  return target;
}

// ── Router ──────────────────────────────────────────────────────────────

function _compilePattern(pattern) {
  const paramNames = [];
  const regex = new RegExp(
    "^" +
      pattern.replace(/\/:([a-zA-Z_][a-zA-Z0-9_]*)/g, (_, name) => {
        paramNames.push(name);
        return "/([^/]+)";
      }) +
      "$"
  );
  return { regex, paramNames };
}

const ROUTES = [
  // Presets (detail before list)
  ["GET", "/comfymodal/studio/presets/:id", async (res, body, params, sid) => _json(res, _sessionOrError(res, sid, () => engine.getPreset(sid, params.id)))],
  ["GET", "/comfymodal/studio/presets", async (res, body, params, sid) => {
    const includeArchived = res._url.searchParams.get("includeArchived") === "1";
    _json(res, _sessionOrError(res, sid, () => engine.listPresets(sid, includeArchived)));
  }],
  ["POST", "/comfymodal/studio/presets", async (res, body) => _json(res, engine.createPreset(res._sid, body || {}), 201)],
  ["PATCH", "/comfymodal/studio/presets/:id", async (res, body, params) => {
    const r = engine.updatePreset(res._sid, params.id, body || {});
    _json(res, r, r._httpStatus || 200);
  }],
  ["DELETE", "/comfymodal/studio/presets/:id", async (res, body, params) => {
    const r = engine.deletePreset(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["POST", "/comfymodal/studio/presets/:id/duplicate", async (res, body, params) => {
    const r = engine.duplicatePreset(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],

  // Snapshots
  ["GET", "/comfymodal/studio/snapshots/:id", async (res, body, params) => {
    const r = engine.getSnapshot(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/studio/snapshots", async (res) => {
    const includeArchived = res._url.searchParams.get("includeArchived") === "1";
    _json(res, engine.listSnapshots(res._sid, includeArchived));
  }],
  ["POST", "/comfymodal/studio/snapshots", async (res, body) => _json(res, engine.createSnapshot(res._sid, body || {}), 201)],
  ["PATCH", "/comfymodal/studio/snapshots/:id", async (res, body, params) => {
    const r = engine.updateSnapshot(res._sid, params.id, body || {});
    _json(res, r, r._httpStatus || 200);
  }],
  ["DELETE", "/comfymodal/studio/snapshots/:id", async (res, body, params) => {
    const r = engine.deleteSnapshot(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["POST", "/comfymodal/studio/snapshots/:id/duplicate", async (res, body, params) => {
    const r = engine.duplicateSnapshot(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],

  // Studio submissions
  ["POST", "/comfymodal/studio/run", async (res, body) => {
    const b = body || {};
    // Modern Studio Workflow run branch: the request carries a
    // workflow_version_id (snake_case or camelCase).  Captures the ENTIRE
    // request body into session state + creates a history-v2 generation.
    // The legacy branch below is untouched for requests without one.
    const workflowVersionId = String(
      b.workflow_version_id || b.workflowVersionId || ""
    ).trim();
    if (workflowVersionId) {
      const r = engine.handleStudioWorkflowRun(res._sid, b);
      if (r && r.status === "error") {
        _json(res, r, r._httpStatus || 400);
      } else {
        _json(res, r, 200);
      }
      return;
    }
    const scenario = _resolvePending(res._sid);
    if (scenario && scenario.submit && scenario.submit.delay) {
      await sleep(scenario.submit.delay);
    }
    const r = engine.handleStudioRun(res._sid, b);
    if (r && r.status === "error") {
      _json(res, r, r._httpStatus || 400);
    } else {
      _json(res, r, 200);
    }
  }],
  // RETIRED_EXECUTION parity (Phase H Wave F): production POST
  // /studio/experiment returns bounded 410 EXPERIMENT_RETIRED with zero
  // experiment creation; the fake mirrors that exactly. Harness-only legacy
  // seeding goes through /__comfymodal_test/legacy-experiment-seed.
  ["POST", "/comfymodal/studio/experiment", async (res) => {
    _json(res, {
      status: "error",
      error_code: "EXPERIMENT_RETIRED",
      message: "Legacy Studio experiment creation was retired in Phase H (Wave F). Modern experiments use POST /studio/experiment-v2.",
    }, 410);
  }],

  // Experiments
  ["GET", "/comfymodal/experiments/:experiment_id", async (res, body, params) => {
    const r = engine.getExperimentStatus(res._sid, params.experiment_id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["POST", "/comfymodal/experiments/:experiment_id/stop-now", async (res, body, params) => {
    const r = engine.stopExperiment(res._sid, params.experiment_id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/experiments", async (res) => {
    _json(res, engine.listExperiments(res._sid));
  }],

  // History (unified + legacy shape)
  ["GET", "/comfymodal/history", async (res) => {
    const params = Object.fromEntries(res._url.searchParams.entries());
    _json(res, engine.listHistory(res._sid, params));
  }],
  ["GET", "/comfymodal/run-history", async (res) => {
    const params = Object.fromEntries(res._url.searchParams.entries());
    _json(res, engine.listRunHistory(res._sid, params));
  }],
  ["PATCH", "/comfymodal/run-history/:run_id/annotations", async (res, body, params) => {
    const r = engine.updateAnnotations(res._sid, params.run_id, body || {});
    _json(res, r, r._httpStatus || 200);
  }],
  ["POST", "/comfymodal/run-history/:run_id/save", async (res, body, params) => {
    const r = engine.saveRunOutput(res._sid, params.run_id, body || {});
    _json(res, r, r._httpStatus || 200);
  }],

  // History V2 (deterministic production-shaped dataset; see fake-backend.mjs)
  ["GET", "/comfymodal/history-v2/feed", async (res) => {
    const params = Object.fromEntries(res._url.searchParams.entries());
    const r = engine.listHistoryV2(res._sid, params);
    if (r && r.status === "error") return _json(res, r, r._httpStatus || 400);
    return _json(res, r, 200);
  }],
  ["GET", "/comfymodal/history-v2/generations/:id", async (res, body, params) => {
    const r = engine.getHistoryV2Generation(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/history-v2/experiments/:id", async (res, body, params) => {
    const r = engine.getHistoryV2Experiment(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],
  // Generate Original — frozen E3B2 production route mirror. 200 carries the
  // production payload (status/outcome/decision/reason/run_id/
  // attempt_status/reused[/executor]); refusals are non-200 with
  // machine-readable {status:"error", code, message} bodies.
  ["POST", "/comfymodal/history-v2/generations/:id/original", async (res, body, params) => {
    const r = engine.generateHistoryV2Original(res._sid, params.id, body || {});
    _json(res, r, r._httpStatus || (r.status === "error" ? 409 : 200));
  }],
  ["POST", "/comfymodal/history-v2/generations/:id/original/retry", async (res, body, params) => {
    const r = engine.retryHistoryV2Original(res._sid, params.id);
    _json(res, r, r._httpStatus || (r.status === "error" ? 409 : 200));
  }],
  // Single Resume — frozen F1A production route mirror (bodyless POST).
  ["POST", "/comfymodal/history-v2/generations/:id/resume", async (res, body, params) => {
    const r = engine.resumeHistoryV2Generation(res._sid, params.id);
    _json(res, r, r._httpStatus || (r.status === "error" ? 409 : 200));
  }],
  // Configured-folder Export — frozen F9 production route mirror (BODYLESS
  // POST; the backend derives generation/output/variant/Settings/filename).
  // 200 ok/already_exported · 404 unknown asset · 400 non-bodyless ·
  // 500 armed export failures (partial:true marks the distinct class).
  ["POST", "/comfymodal/history-v2/assets/:id/export", async (res, body, params) => {
    const r = engine.exportHistoryV2Asset(res._sid, params.id, body);
    _json(res, r, r._httpStatus || (r.status === "error" ? 500 : 200));
  }],
  // Modern Experiment V2 (D5) — additive deterministic parity for the
  // production contract (experiment_modern_routes.py / freeze §11).  Placed
  // after the History V2 detail route and before any catch-all conflicts;
  // anchored regexes keep these distinct from the legacy routes above.
  ["POST", "/comfymodal/studio/experiment-v2", async (res, body) => {
    const r = engine.handleModernExperimentCreate(res._sid, body || {});
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/history-v2/experiments/:id/status", async (res, body, params) => {
    const r = engine.getModernExperimentStatus(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["POST", "/comfymodal/history-v2/experiments/:id/cancel", async (res, body, params) => {
    const r = engine.cancelModernExperiment(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["POST", "/comfymodal/history-v2/experiments/:id/resume", async (res, body, params) => {
    const r = engine.resumeModernExperiment(res._sid, params.id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["POST", "/comfymodal/history-v2/experiments/:id/cells/:cell_id/retry", async (res, body, params) => {
    const r = engine.retryModernCell(res._sid, params.id, params.cell_id);
    _json(res, r, r._httpStatus || 200);
  }],
  ["PATCH", "/comfymodal/history-v2/generations/:id/favorite", async (res, body, params) => {
    const r = engine.setHistoryV2Favorite(res._sid, "generation", params.id, body);
    _json(res, r, r._httpStatus || 200);
  }],
  ["PATCH", "/comfymodal/history-v2/generations/:id/note", async (res, body, params) => {
    const r = engine.setHistoryV2Note(res._sid, "generation", params.id, body);
    _json(res, r, r._httpStatus || 200);
  }],
  ["PATCH", "/comfymodal/history-v2/generations/:id/featured", async (res, body, params) => {
    const r = engine.setHistoryV2Featured(res._sid, params.id, body);
    _json(res, r, r._httpStatus || 200);
  }],
  ["PATCH", "/comfymodal/history-v2/experiments/:id/favorite", async (res, body, params) => {
    const r = engine.setHistoryV2Favorite(res._sid, "experiment", params.id, body);
    _json(res, r, r._httpStatus || 200);
  }],
  ["PATCH", "/comfymodal/history-v2/experiments/:id/note", async (res, body, params) => {
    const r = engine.setHistoryV2Note(res._sid, "experiment", params.id, body);
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/history-v2/assets/:id", async (res, body, params) => {
    const a = engine.getAsset(res._sid, params.id);
    if (!a.ok) return _error(res, a.status === 502 ? "asset upstream unavailable" : "asset not found", a.status || 404);
    _buffer(res, a.bytes, a.contentType);
  }],

  // Deploy status + profile level (deterministic defaults, session-scoped level)
  ["GET", "/comfymodal/deploy/status", async (res) => _json(res, engine.getDeployStatus(res._sid))],
  ["GET", "/comfymodal/auth/status", async (res) => _json(res, { status: "ok", connected: true })],
  ["GET", "/comfymodal/health", async (res) => _json(res, { status: "ok", message: "Fake runtime ready" })],
  ["GET", "/comfymodal/profile/level", async (res) => _json(res, engine.getProfileLevel(res._sid))],
  ["POST", "/comfymodal/profile/level", async (res, body) => {
    const r = engine.setProfileLevel(res._sid, body);
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/workspaces", async (res) => _json(res, engine.listWorkspaces(res._sid))],
  ["POST", "/comfymodal/workspaces", async (res, body) => {
    const r = engine.upsertWorkspace(res._sid, body || {});
    _json(res, r, r._httpStatus || 200);
  }],
  ["POST", "/comfymodal/workspaces/active", async (res, body) => {
    const r = engine.activateWorkspace(res._sid, body || {});
    _json(res, r, r._httpStatus || 200);
  }],

  // Assets & outputs
  ["GET", "/comfymodal/assets/:asset_id", async (res, body, params) => {
    const a = engine.getAsset(res._sid, params.asset_id);
    if (!a.ok) return _error(res, a.status === 502 ? "asset upstream unavailable" : "asset not found", a.status || 404);
    _buffer(res, a.bytes, a.contentType);
  }],
  ["GET", "/comfymodal/studio/outputs/:filename", async (res, body, params) => {
    const o = engine.getOutput(res._sid, params.filename);
    if (!o.ok) return _error(res, "output not found", 404);
    _buffer(res, o.bytes, o.contentType);
  }],

  // Backends & config
  ["GET", "/comfymodal/studio/backends", async (res) => {
    _json(res, engine.getBackends(res._sid));
  }],
  ["GET", "/comfymodal/config", async (res) => {
    _json(res, engine.getConfig(res._sid));
  }],
  ["POST", "/comfymodal/config", async (res, body) => {
    _json(res, engine.setConfig(res._sid, body || {}));
  }],

  // Studio Workflows (deterministic fake dataset; see _studioSeed above).
  // Static paths before /workflows/:id catch-alls (regexes are anchored).
  // Picker list/search (leaf 1.2.1): the legacy wf_fake record goes through
  // the SAME search/tag/folder/favorite filter semantics as the seeded
  // platform workflows so picker search results stay deterministic.
  ["GET", "/comfymodal/studio/workflows/folders", async (res) => {
    const seeded = engine.listFakeWorkflows(res._sid, {});
    const set = new Set();
    (Array.isArray(seeded.workflows) ? seeded.workflows : []).forEach((w) => {
      if (w && w.folder) set.add(String(w.folder));
    });
    const legacy = _studioSeed(res._sid).workflow;
    if (legacy && legacy.folder) set.add(String(legacy.folder));
    _json(res, { status: "ok", folders: Array.from(set).sort() });
  }],
  ["GET", "/comfymodal/studio/workflows/tags", async (res) => _json(res, { status: "ok", tags: [] })],
  ["GET", "/comfymodal/studio/workflows", async (res) => {
    // The seeded platform workflows (wf_text2img / wf_incomplete / wf_fail)
    // plus the legacy wf_fake record from the dependency/import surface.
    const s = _studioSeed(res._sid);
    const q = Object.fromEntries(res._url.searchParams.entries());
    const seeded = engine.listFakeWorkflows(res._sid, q);
    const legacy = Object.assign({}, s.workflow);
    const workflows = (_legacyMatchesPickerQuery(legacy, q) ? [legacy] : []).concat(
      Array.isArray(seeded.workflows) ? seeded.workflows : []
    );
    _json(res, { status: "ok", workflows });
  }],
  ["POST", "/comfymodal/studio/workflows/import", async (res, body) => {
    const s = _studioSeed(res._sid);
    const name = (body && body.name) || "Imported Workflow";
    s.workflow = _fakeWorkflow();
    s.workflow.name = name;
    s.version = _fakeVersion();
    const deps = _fakeDependenciesPayload();
    _json(res, {
      status: "ok",
      workflow: s.workflow,
      version: s.version,
      dependency_summary: {
        models: deps.models,
        custom_nodes: deps.custom_nodes,
        summary: deps.summary,
      },
    }, 201);
  }],
  ["GET", "/comfymodal/studio/workflows/:id/versions", async (res, body, params) => {
    const s = _studioSeed(res._sid);
    // Seeded workflow → seeded versions; legacy wf_fake keeps its version.
    if (params.id !== s.workflow.workflow_id) {
      const r = engine.listFakeWorkflowVersions(res._sid, params.id);
      if (r.status === "ok") return _json(res, r);
      return _error(res, "workflow not found", 404);
    }
    const v = Object.assign({}, s.version);
    delete v.dependency_summary;
    _json(res, { status: "ok", versions: [v] });
  }],
  ["GET", "/comfymodal/studio/workflows/:id/run-context", async (res, body, params) => {
    const versionId = res._url.searchParams.get("version_id") || "";
    const r = engine.getFakeWorkflowRunContext(res._sid, params.id, versionId);
    _json(res, r, r._httpStatus || 200);
  }],
  ["PATCH", "/comfymodal/studio/workflows/:id", async (res, body, params) => {
    const r = engine.updateFakeWorkflow(res._sid, params.id, body || {});
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/studio/workflows/versions/:vid/dependencies", async (res) => {
    _json(res, _fakeDependenciesPayload());
  }],
  ["GET", "/comfymodal/studio/workflows/versions/:vid/presets", async (res, body, params) => {
    const r = engine.listFakeVersionPresets(res._sid, params.vid);
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/studio/workflows/versions/:vid/mapping", async (res, body, params) => {
    if (!_resolveFakeVersion(res._sid, params.vid)) return _error(res, "version not found", 404);
    _json(res, { status: "ok", mapping: _effectiveFakeMapping(res._sid, params.vid) });
  }],
  // Binding candidates + creation (leaf 1.2.1 follow-up). Candidates mirror
  // the workflows-mock contract {status, candidates:{entries,
  // output_node_id}}: the effective mapping's entries when the version is
  // mapped, otherwise an empty (but well-shaped) proposal set. Creation is
  // immutable like production: a second POST for a mapped version is 409.
  ["GET", "/comfymodal/studio/workflows/versions/:vid/mapping/candidates", async (res, body, params) => {
    if (!_resolveFakeVersion(res._sid, params.vid)) return _error(res, "version not found", 404);
    const mapping = _effectiveFakeMapping(res._sid, params.vid);
    _json(res, {
      status: "ok",
      candidates: {
        entries: mapping && Array.isArray(mapping.entries) ? mapping.entries : [],
        output_node_id: (mapping && mapping.output_node_id) || null,
      },
    });
  }],
  ["POST", "/comfymodal/studio/workflows/versions/:vid/mapping", async (res, body, params) => {
    if (!_resolveFakeVersion(res._sid, params.vid)) return _error(res, "version not found", 404);
    if (_effectiveFakeMapping(res._sid, params.vid)) {
      return _json(res, {
        status: "error",
        message: "This version already has an immutable mapping. Create a new version to change the mapping.",
      }, 409);
    }
    const b = body || {};
    _localBindingSeq += 1;
    const mapping = {
      mapping_id: `wmap_local_${_localBindingSeq}`,
      workflow_version_id: params.vid,
      output_node_id: b.output_node_id || null,
      entries: Array.isArray(b.entries) ? b.entries : [],
    };
    LOCAL_BINDINGS.set(_bindingKey(res._sid, params.vid), mapping);
    _json(res, { status: "ok", mapping });
  }],
  ["GET", "/comfymodal/studio/workflows/versions/:vid", async (res, body, params) => {
    const s = _studioSeed(res._sid);
    if (params.vid !== s.version.workflow_version_id) {
      const r = engine.getFakeWorkflowVersion(res._sid, params.vid);
      if (r.status === "ok") return _json(res, r);
      return _error(res, "version not found", 404);
    }
    _json(res, { status: "ok", version: s.version });
  }],
  ["GET", "/comfymodal/studio/workflows/presets/:pid", async (res, body, params) => {
    const r = engine.getFakeWorkflowPreset(res._sid, params.pid);
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/studio/workflows/:id", async (res, body, params) => {
    const s = _studioSeed(res._sid);
    if (params.id !== s.workflow.workflow_id) {
      const r = engine.getFakeWorkflow(res._sid, params.id);
      if (r.status === "ok") return _json(res, r);
      return _error(res, "workflow not found", 404);
    }
    _json(res, { status: "ok", workflow: s.workflow });
  }],

  // Studio Workflow Portability (G12 deterministic contract payloads).
  // Anchored regexes keep these distinct from /versions/:id catch-alls.
  ["GET", "/comfymodal/studio/workflows/versions/:vid/portability", async (res, body, params) => {
    const r = engine.getFakePortabilityReport(res._sid, params.vid);
    _json(res, r, r._httpStatus || 200);
  }],
  ["GET", "/comfymodal/studio/workflows/versions/:vid/export", async (res, body, params) => {
    const includePresets = res._url.searchParams.get("include_presets") === "1";
    const r = engine.exportFakeWorkflowManifest(res._sid, params.vid, includePresets);
    if (!r.ok) {
      return _json(res, { status: "error", code: r.error_code, message: r.message }, r.status || 400);
    }
    const body2 = Buffer.from(r.body, "utf8");
    res.writeHead(200, {
      "Content-Type": "application/json; charset=utf-8",
      "Content-Length": body2.length,
      "Content-Disposition": 'attachment; filename="' + r.filename + '"',
      "Cache-Control": "no-store",
    });
    res.end(body2);
  }],
  ["POST", "/comfymodal/studio/workflows/import-manifest", async (res, body) => {
    const dryRun = res._url.searchParams.get("dry_run") !== "0";
    const r = dryRun
      ? engine.previewFakeManifestImport(res._sid, body || {})
      : engine.commitFakeManifestImport(res._sid, body || {});
    _json(res, r, r._httpStatus || (r.status === "error" ? 400 : 200));
  }],

  // Studio Model Library (deterministic fake dataset).
  ["GET", "/comfymodal/studio/models/types", async (res) => _json(res, {
    status: "ok",
    types: ["checkpoint", "unet", "clip", "vae", "lora", "controlnet", "upscaler", "other"],
  })],
  ["POST", "/comfymodal/studio/models/rescan", async (res) => _json(res, {
    status: "ok",
    summary: { added: 0, updated: 0, removed: 0, unchanged: 3, hashed: 0, placeholders: 0, total: 3 },
  })],
  ["POST", "/comfymodal/studio/models/install-request", async (res, body) => {
    const b = body || {};
    const url = b.url || "";
    const sourceKind = url.indexOf("huggingface") !== -1 ? "hf" : url.indexOf("civitai") !== -1 ? "civitai" : "url";
    _json(res, {
      status: "ok",
      request: {
        folder: b.folder || "",
        filename: b.filename || "",
        url,
        source_kind: sourceKind,
        requires_hf_token: sourceKind === "hf",
        requires_civitai_token: sourceKind === "civitai",
        approved: true,
      },
      note: "Approval recorded. No download was started \u2014 the request is queued for the operator.",
    });
  }],
  ["GET", "/comfymodal/studio/models", async (res) => {
    const s = _studioSeed(res._sid);
    const q = res._url.searchParams;
    let list = s.models;
    const search = (q.get("search") || "").toLowerCase();
    if (search) {
      list = list.filter((m) =>
        String(m.display_name || "").toLowerCase().indexOf(search) !== -1 ||
        String(m.filename || "").toLowerCase().indexOf(search) !== -1
      );
    }
    const type = q.get("type") || "";
    if (type) list = list.filter((m) => m.model_type === type);
    const state = q.get("state") || "";
    if (state === "installed") list = list.filter((m) => m.installed === true);
    else if (state === "missing") list = list.filter((m) => m.installed !== true);
    _json(res, { status: "ok", models: list, total: list.length, scan_hint: "ok" });
  }],
  ["GET", "/comfymodal/studio/models/:id", async (res, body, params) => {
    const s = _studioSeed(res._sid);
    const m = s.models.find((x) => x.model_id === params.id);
    if (!m) return _error(res, "model not found", 404);
    _json(res, { status: "ok", model: Object.assign({}, m) });
  }],
  ["PATCH", "/comfymodal/studio/models/:id", async (res, body, params) => {
    const s = _studioSeed(res._sid);
    const m = s.models.find((x) => x.model_id === params.id);
    if (!m) return _error(res, "model not found", 404);
    const b = body || {};
    if (b.display_name !== undefined) m.display_name = String(b.display_name);
    if (b.provider !== undefined) m.provider = String(b.provider);
    if (b.revision !== undefined) m.revision = String(b.revision);
    if (b.notes !== undefined) m.notes = String(b.notes);
    if (b.tags !== undefined) m.tags = Array.isArray(b.tags) ? b.tags.map(String) : [];
    if (b.source_urls !== undefined) m.source_urls = Array.isArray(b.source_urls) ? b.source_urls.map(String) : [];
    m.updated_at = _isoNow();
    _json(res, { status: "ok", model: Object.assign({}, m) });
  }],

  // Studio Custom Nodes (deterministic fake dataset).
  ["GET", "/comfymodal/studio/custom-nodes", async (res) => {
    const s = _studioSeed(res._sid);
    _json(res, {
      status: "ok",
      custom_nodes: s.customNodes.map((n) => Object.assign({}, n)),
      core_classes: s.coreClasses,
    });
  }],
  ["POST", "/comfymodal/studio/custom-nodes/refresh", async (res) => {
    const s = _studioSeed(res._sid);
    _json(res, {
      status: "ok",
      custom_nodes: s.customNodes.map((n) => Object.assign({}, n)),
      core_classes: s.coreClasses,
    });
  }],
  ["POST", "/comfymodal/studio/custom-nodes/install-request", async (res, body) => {
    const b = body || {};
    _json(res, {
      status: "ok",
      request: {
        name: b.name || "",
        repo_url: b.repo_url || "",
        revision: b.revision || "",
        approved: true,
      },
      note: "Approval recorded. No download was started \u2014 the request is queued for the operator.",
    });
  }],
];

const COMPILED = ROUTES.map(([method, pattern, handler]) => {
  const { regex, paramNames } = _compilePattern(pattern);
  return { method, regex, paramNames, handler };
});

function _resolvePending(sessionId) {
  try {
    return engine.getSession(sessionId).pendingScenario;
  } catch {
    return null;
  }
}

// ── Test-control endpoints ──────────────────────────────────────────────

async function handleTestControl(url, req, res, body, pathname) {
  const sid = _sessionIdFromRequest(req, url, body);

  if (pathname === "/__comfymodal_test/session" && req.method === "POST") {
    const { sessionId } = engine.createSession();
    return _json(res, { status: "ok", sessionId });
  }
  if (pathname === "/__comfymodal_test/events" && req.method === "GET") {
    const cursor = url.searchParams.get("cursor");
    return _json(res, engine.drainEvents(sid, cursor == null ? 0 : parseInt(cursor, 10) || 0));
  }
  if (pathname === "/__comfymodal_test/scenario" && req.method === "POST") {
    const r = engine.setPendingScenario(sid, body && body.scenario, (body && body.overrides) || null);
    return _json(res, r, r.status === "error" ? 400 : 200);
  }
  // Harness-only legacy experiment seed (Phase H Wave F): production
  // /studio/experiment is retired (410), but specs that must exercise
  // STALE legacy-shaped records still need a way to create one without
  // touching the retired route. This control endpoint delegates directly
  // to the engine creator and is never called by product code.
  if (pathname === "/__comfymodal_test/legacy-experiment-seed" && req.method === "POST") {
    const r = engine.handleStudioExperiment(sid, body || {});
    if (r && r.status === "error") {
      return _json(res, r, r._httpStatus || 400);
    }
    return _json(res, r, 200);
  }
  if (pathname === "/__comfymodal_test/history-seed" && req.method === "POST") {
    const r = engine.seedHistory(sid, body && body.scenario);
    return _json(res, r, r.status === "error" ? 400 : 200);
  }
  if (pathname === "/__comfymodal_test/history-v2-fail" && req.method === "POST") {
    const r = engine.setHistoryV2FailMode(sid, body && body.mode);
    return _json(res, r, r.status === "error" ? 400 : 200);
  }
  if (pathname === "/__comfymodal_test/original-script" && req.method === "POST") {
    const r = engine.setOriginalScript(sid, body || {});
    return _json(res, r, r.status === "error" ? 400 : 200);
  }
  if (pathname === "/__comfymodal_test/asset-fail" && req.method === "POST") {
    const r = engine.armAssetFailure(sid, body || {});
    return _json(res, r, r.status === "error" ? 400 : 200);
  }
  if (pathname === "/__comfymodal_test/export-fail" && req.method === "POST") {
    const r = engine.armExportFailure(sid, body || {});
    return _json(res, r, r.status === "error" ? 400 : 200);
  }
  if (pathname === "/__comfymodal_test/export-delete" && req.method === "POST") {
    const r = engine.deleteExportedFile(sid, body || {});
    return _json(res, r, r.status === "error" ? 400 : 200);
  }
  if (pathname === "/__comfymodal_test/emit" && req.method === "POST") {
    const r = engine.injectEvent(sid, { type: body && body.type, detail: body && body.detail });
    return _json(res, r, r.status === "error" ? 400 : 200);
  }
  if (pathname === "/__comfymodal_test/modern-experiment-state" && req.method === "POST") {
    const r = engine.setModernExperimentState(sid, body);
    return _json(res, r, r.status === "error" ? (r._httpStatus || 400) : 200);
  }
  if (pathname === "/__comfymodal_test/portability" && req.method === "POST") {
    const r = engine.armPortability(sid, body || {});
    return _json(res, r, r.status === "error" ? (r._httpStatus || 400) : 200);
  }
  if (pathname === "/__comfymodal_test/portability-export-fail" && req.method === "POST") {
    const r = engine.armPortabilityExportFail(sid, body || {});
    return _json(res, r, r.status === "error" ? (r._httpStatus || 400) : 200);
  }
  if (pathname === "/__comfymodal_test/import-manifest-arm" && req.method === "POST") {
    const r = engine.armManifestImport(sid, body || {});
    return _json(res, r, r.status === "error" ? (r._httpStatus || 400) : 200);
  }
  if (pathname === "/__comfymodal_test/state" && req.method === "GET") {
    return _json(res, _sessionOrError(res, sid, () => engine.dumpState(sid)));
  }
  return _error(res, `unhandled test-control endpoint: ${req.method} ${pathname}`, 404);
}

// ── Main request handler ────────────────────────────────────────────────

async function handleRequest(req, res) {
  const url = new URL(req.url, "http://localhost");
  const pathname = url.pathname;
  const method = req.method || "GET";
  res._url = url;

  if (process.env.FAKE_SERVER_DEBUG === "1") {
    console.log(`[fake] ${method} ${pathname}`);
  }

  // Test control
  if (pathname.startsWith("/__comfymodal_test/")) {
    const body = ["POST", "PATCH", "PUT"].includes(method) ? await _readBody(req) : null;
    try {
      return await handleTestControl(url, req, res, body, pathname);
    } catch (err) {
      return _json(res, { status: "error", message: "test-control error: " + err.message }, 500);
    }
  }

  // Static harness files
  if (method === "GET") {
    if (pathname === "/") return _serveFile(res, path.join(HARNESS_DIR, "index.html"), "text/html; charset=utf-8");
    if (pathname === "/harness-bootstrap.js") return _serveFile(res, path.join(HARNESS_DIR, "harness-bootstrap.js"));
    if (pathname === "/scripts/api.js") return _serveFile(res, path.join(HARNESS_DIR, "scripts", "api.js"));
    if (pathname === "/scripts/app.js") return _serveFile(res, path.join(HARNESS_DIR, "scripts", "app.js"));
    if (pathname.startsWith("/extensions/comfymodal-modal/") || pathname.startsWith("/extensions/comfyui-modal/")) {
      const prefix = pathname.startsWith("/extensions/comfyui-modal/") ? "/extensions/comfyui-modal" : "/extensions/comfymodal-modal";
      const rel = pathname.slice(prefix.length);
      const target = _resolveInside(WEB_DIR, rel);
      if (target) return _serveFile(res, target);
      return _error(res, "bad extension path", 400);
    }
    if (pathname === "/view") {
      const filename = url.searchParams.get("filename");
      if (filename) {
        const o = engine.getOutput(_getCookie(req, "comfymodal_fake_session") || DEFAULT_SESSION, filename);
        if (o.ok) return _buffer(res, o.bytes, o.contentType);
      }
      return _error(res, "output not found", 404);
    }
  }

  // Engine REST routes
  if (pathname.startsWith("/comfymodal/")) {
    const body = ["POST", "PATCH", "PUT"].includes(method) ? await _readBody(req) : null;
    const sid = _sessionIdFromRequest(req, url, body);
    res._sid = sid;
    for (const entry of COMPILED) {
      if (entry.method !== method) continue;
      const match = pathname.match(entry.regex);
      if (!match) continue;
      const params = {};
      for (let i = 0; i < entry.paramNames.length; i++) {
        params[entry.paramNames[i]] = decodeURIComponent(match[i + 1]);
      }
      try {
        const r = await entry.handler(res, body, params, sid);
        if (r !== undefined && r !== null) return r;
        return;
      } catch (err) {
        return _json(res, { status: "error", message: "handler error: " + err.message }, 500);
      }
    }
    // Unhandled /comfymodal/** — never hang, always JSON error
    return _error(res, `unhandled fake endpoint: ${method} ${pathname}`, 404);
  }

  if (pathname === "/favicon.ico") {
    res.writeHead(204);
    return res.end();
  }

  return _error(res, `not found: ${pathname}`, 404);
}

// ── Server factory ──────────────────────────────────────────────────────

export function createFakeServer(options = {}) {
  const port = options.port || Number(process.env.STUDIO_FAKE_PORT) || 8377;
  const server = http.createServer((req, res) => {
    handleRequest(req, res).catch((err) => {
      try {
        _json(res, { status: "error", message: "unhandled: " + err.message }, 500);
      } catch { /* socket gone */ }
    });
  });
  return { server, port };
}

export function startServer(options = {}) {
  const { server, port } = createFakeServer(options);
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      const actual = server.address().port;
      console.log(`[fake-server] Studio fake backend listening on http://127.0.0.1:${actual} (web: ${WEB_DIR})`);
      resolve({ server, port: actual, url: `http://127.0.0.1:${actual}` });
    });
  });
}

// ── Standalone entrypoint ───────────────────────────────────────────────

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMain) {
  startServer().then(({ url }) => {
    console.log(`[fake-server] Ready at ${url} — harness: ${url}/?session=probe`);
  }).catch((err) => {
    console.error("[fake-server] failed to start:", err);
    process.exit(1);
  });
}
