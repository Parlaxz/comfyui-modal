// Modal Studio — Workflows Page
//
// Workflow library, graph import / manual creation, workflow detail
// (versions, dependencies placeholder, mapping, presets, copy-forward),
// the mapping editor, and the preset editor.
//
// Render contract: export function renderWorkflows(state, context) → DOM node.
//   state   — shell state (unused directly; view state lives in this module)
//   context — { apiBase, setPage, comfyApi }
//
// All DOM is built through el() from studio-ui.js. No innerHTML with data.

import { el, statusBadge } from "./studio-ui.js";
import { renderModelLibraryView, renderDependencySection, renderModelPicker } from "./studio-model-library.js";
import {
  listWorkflows,
  createWorkflow,
  importWorkflow,
  getWorkflow,
  updateWorkflow,
  listWorkflowFolders,
  listWorkflowTags,
  setWorkflowDefaultPreset,
  clearWorkflowDefaultPreset,
  getWorkflowRunContext,
  listWorkflowVersions,
  captureWorkflowVersion,
  getWorkflowVersion,
  getVersionState,
  getMapping,
  createMapping,
  getMappingCandidates,
  createMappingRevision,
  listVersionPresets,
  createVersionPreset,
  getWorkflowPreset,
  updateWorkflowPreset,
  deleteWorkflowPreset,
  duplicateWorkflowPreset,
  copyPresetToVersion,
  bulkCopyPresetsToVersion,
  getVersionDependencies,
  listModels,
} from "./studio-backend-api.js";

// ── Module-level view state ────────────────────────────────────────────────
// Persists across shell re-renders so navigating away and back preserves
// the selected workflow, version, filters, and editor mode.

const _view = {
  mode: "library",                 // "library" | "detail" | "models"
  selectedWorkflowId: "",
  selectedVersionId: "",
  editorMode: "",                  // "" | "mapping" | "preset"
  activePresetId: "",              // preset being edited; "" = new preset
  detailEditing: false,
  revisionConfirm: false,          // mapping immutability confirmation open
  capturingVersion: false,
  importMode: "",                  // "" | "graph" | "manual" (dialog section)
  filters: { query: "", tag: "", folder: "", favoritesOnly: false },
  modelsData: {
    models: [],
    scanHint: "not_scanned",
    filters: { query: "", type: "", state: "" },
    types: [],
    customNodes: [],
    loading: false,
    _loaded: false,
  },
  modelsCache: null,               // library models for the preset model picker
  modelsCacheState: "idle",        // "idle" | "loading" | "loaded" | "failed"
  data: {
    workflows: null,
    tags: [],
    folders: [],
    workflow: null,
    versions: [],
    version: null,
    presets: [],
    mapping: null,
    mappingVersionId: "",
    candidates: null,
    candidatesVersionId: "",
    editPreset: null,
    copyResults: null,
    notice: null,
    presetIncomplete: null,
    loadError: null,
    dependencies: null,
  },
};

let _currentToken = 0;
let _searchTimer = null;
let _importEscHandler = null;

// ── Small pure helpers ─────────────────────────────────────────────────────

function _unwrap(apiData, key) {
  if (apiData === null || apiData === undefined) return null;
  if (Array.isArray(apiData)) return apiData;
  if (typeof apiData === "object") {
    if (apiData.status === "error") return null;
    if (key && apiData[key] !== undefined) return apiData[key];
    return apiData;
  }
  return apiData;
}

function _shortDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  try {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch (e) {
    return String(iso);
  }
}

function _shortHash(h) {
  if (!h) return "";
  const s = String(h);
  return s.length > 10 ? s.slice(0, 10) : s;
}

function _errorText(result) {
  if (!result) return "unknown error";
  return result.message
    || result.error
    || (result._httpStatus ? "HTTP " + result._httpStatus : "request failed");
}

function _reasonText(r) {
  if (typeof r === "string") return r;
  if (r && typeof r === "object") {
    if (typeof r.message === "string") return r.message;
    if (r.kind && r.label) return r.kind + ": " + r.label;
    try { return JSON.stringify(r); } catch (e) { return String(r); }
  }
  return String(r);
}

function _reasonList(reasons, extraClass) {
  const ul = el("ul", { class: "comfymodal-studio-reason-list" + (extraClass ? " " + extraClass : "") });
  (reasons || []).forEach((r) => ul.appendChild(el("li", { text: _reasonText(r) })));
  return ul;
}

function _stateBadge(state, testid) {
  const status = state && state.status ? state.status : "unknown";
  const text = status === "ready" ? "Ready" : status === "incomplete" ? "Incomplete" : String(status);
  const kind = status === "ready" ? "ok" : status === "incomplete" ? "warn" : "neutral";
  const badge = statusBadge(text, kind);
  if (testid) badge.setAttribute("data-testid", testid);
  return badge;
}

function _chip(text) {
  return el("span", { class: "comfymodal-studio-wf-chip", text: text });
}

function _field(label, input) {
  return el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: label }), input]);
}

// ── Control rendering (shared by mapping + preset editors) ────────────────

function _controlKind(entry) {
  const ck = entry && entry.control_kind;
  if (ck) return ck;
  const k = entry && entry.kind;
  return k || "string";
}

function _roleName(entry) {
  return (entry && (entry.display_name || entry.semantic_role)) || "control";
}

function _roleInfo(entry) {
  const parts = [];
  if (entry.node_id != null) parts.push("node " + entry.node_id);
  if (entry.input_name) parts.push(entry.input_name);
  if (entry.output_name) parts.push("-> " + entry.output_name);
  if (entry.data_type) parts.push(entry.data_type);
  return parts.join(" \u00b7 ");
}

function _numHint(entry) {
  const parts = [];
  if (entry.minimum != null) parts.push("min " + entry.minimum);
  if (entry.maximum != null) parts.push("max " + entry.maximum);
  if (entry.step != null) parts.push("step " + entry.step);
  return parts.length ? parts.join(" \u00b7 ") : "";
}

function _makeControl(entry, value) {
  const kind = _controlKind(entry);
  if (kind === "enum") {
    const sel = el("select", { class: "comfymodal-studio-select" });
    const opts = entry.enum_options || [];
    opts.forEach((opt) => sel.appendChild(el("option", { value: String(opt), text: String(opt) })));
    if (value != null && opts.indexOf(value) !== -1) sel.value = String(value);
    else if (opts.length) sel.value = String(opts[0]);
    return sel;
  }
  if (kind === "boolean") {
    const cb = el("input", { type: "checkbox", class: "comfymodal-studio-wf-checkbox" });
    cb.checked = !!value;
    return cb;
  }
  if (kind === "integer") {
    const inp = el("input", { type: "number", class: "comfymodal-studio-number-input", step: entry.step != null ? String(entry.step) : "1" });
    if (entry.minimum != null) inp.setAttribute("min", String(entry.minimum));
    if (entry.maximum != null) inp.setAttribute("max", String(entry.maximum));
    if (value != null) inp.value = String(value);
    return inp;
  }
  if (kind === "number") {
    const inp = el("input", { type: "number", class: "comfymodal-studio-number-input", step: entry.step != null ? String(entry.step) : "any" });
    if (entry.minimum != null) inp.setAttribute("min", String(entry.minimum));
    if (entry.maximum != null) inp.setAttribute("max", String(entry.maximum));
    if (value != null) inp.value = String(value);
    return inp;
  }
  if (kind === "multiline") {
    const ta = el("textarea", { class: "comfymodal-studio-textarea", rows: 2 });
    if (value != null) ta.value = String(value);
    return ta;
  }
  // string / file / image / node → text input
  const inp = el("input", { type: "text", class: "comfymodal-studio-wf-input" });
  if (value != null) inp.value = String(value);
  if (kind === "node") inp.setAttribute("readonly", "");
  return inp;
}

// Falsy values (0, 0.0, false, "") are preserved exactly — never dropped.
function _readControlValue(entry, ctrl) {
  if (!ctrl) return undefined;
  const kind = _controlKind(entry);
  if (kind === "boolean") return !!ctrl.checked;
  if (kind === "integer" || kind === "number") {
    if (ctrl.value === "" || ctrl.value == null) return 0;
    const n = Number(ctrl.value);
    return isNaN(n) ? 0 : n;
  }
  return ctrl.value;
}

// ── Folder tree helpers ───────────────────────────────────────────────────

function _collectFolderPaths(folders, prefix, out) {
  if (!Array.isArray(folders)) return;
  folders.forEach((f) => {
    if (f == null) return;
    if (typeof f === "string") {
      out.push(prefix ? prefix + "/" + f : f);
    } else if (typeof f === "object") {
      const name = f.name || f.label || f.path || "";
      if (!name) return;
      const path = prefix ? prefix + "/" + name : name;
      out.push(path);
      _collectFolderPaths(f.children, path, out);
    }
  });
}

function _folderTree(paths) {
  const root = { name: "", path: "", children: {} };
  (paths || []).forEach((p) => {
    const segs = String(p).split(/[\/\\]+/).filter(Boolean);
    let node = root;
    let cur = "";
    segs.forEach((s) => {
      cur = cur ? cur + "/" + s : s;
      if (!node.children[s]) node.children[s] = { name: s, path: cur, children: {} };
      node = node.children[s];
    });
  });
  return root;
}

function _suggestNameFromGraph(graphJson) {
  try {
    if (graphJson && Array.isArray(graphJson.nodes)) {
      for (const n of graphJson.nodes) {
        if (n && (n.type === "Note" || n.type === "note")) {
          const text = String((n.widgets_values && n.widgets_values[0]) || "").trim();
          if (text) return text.slice(0, 120);
        }
      }
    }
  } catch (e) { /* fall through to timestamp */ }
  const d = new Date();
  const pad = (x) => String(x).padStart(2, "0");
  return "Workflow " + d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate())
    + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
}

function _modelLabel(m) {
  if (m == null) return "?";
  if (typeof m === "string") return m;
  if (typeof m === "object") {
    const parts = [];
    if (m.name) parts.push(m.name);
    if (m.version != null) parts.push("v" + m.version);
    if (m.type) parts.push(m.type);
    return parts.length ? parts.join(" \u00b7 ") : JSON.stringify(m);
  }
  return String(m);
}

function _showStatus(statusEl, text, isError) {
  statusEl.style.display = "block";
  statusEl.textContent = text;
  statusEl.classList.remove("error");
  if (isError) statusEl.classList.add("error");
}

// ── Main render entry point ───────────────────────────────────────────────

export function renderWorkflows(state, context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  const setPage = (context && context.setPage) || function () {};
  const token = ++_currentToken;

  const root = el("div", { class: "comfymodal-studio-workflows", "data-testid": "workflows-page" });

  // Mount-local rendering refs
  let gridEl = null;
  let mappingControls = {};
  let presetRefs = { values: {}, rec: {}, models: {}, exposed: {}, loraRows: [] };
  let presetEntries = [];
  const expandedVersions = new Set();

  function stale() { return token !== _currentToken; }

  function render() {
    while (root.firstChild) root.removeChild(root.firstChild);
    if (_view.mode === "detail") {
      root.appendChild(renderDetailView());
      if (_view.editorMode === "mapping") ensureMappingEditorData();
      else if (_view.editorMode === "preset") ensurePresetEditorData();
    } else if (_view.mode === "models") {
      root.appendChild(renderModelLibraryView({ apiBase, view: _view, refresh: render }));
    } else {
      root.appendChild(renderLibraryView());
    }
  }

  // ── Navigation ──────────────────────────────────────────────────────────

  function openWorkflowDetail(wfId, versionId, notice) {
    _view.mode = "detail";
    _view.selectedWorkflowId = wfId;
    _view.selectedVersionId = versionId || "";
    _view.editorMode = "";
    _view.activePresetId = "";
    _view.detailEditing = false;
    _view.revisionConfirm = false;
    _view.data.editPreset = null;
    _view.data.copyResults = null;
    _view.data.presetIncomplete = null;
    _view.data.notice = notice ? { text: notice, error: false } : null;
    _view.data.loadError = null;
    _view.data.workflow = null;
    _view.data.versions = [];
    _view.data.version = null;
    _view.data.presets = [];
    _view.data.mapping = null;
    _view.data.dependencies = null;
    render();
    loadDetailData();
  }

  function goToLibrary() {
    _view.mode = "library";
    _view.editorMode = "";
    _view.activePresetId = "";
    _view.detailEditing = false;
    _view.revisionConfirm = false;
    _view.importMode = "";
    _view.data.notice = null;
    _view.data.copyResults = null;
    render();
    loadLibrary();
  }

  // ── Library ─────────────────────────────────────────────────────────────

  function applyFilters(list) {
    const q = _view.filters.query.trim().toLowerCase();
    return list.filter((w) => {
      if (q) {
        const hay = [w.name, w.description, (w.tags || []).join(" ")].filter(Boolean).join(" ").toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      if (_view.filters.tag && !(w.tags || []).includes(_view.filters.tag)) return false;
      if (_view.filters.folder && !String(w.folder || "").startsWith(_view.filters.folder)) return false;
      if (_view.filters.favoritesOnly && !w.favorite) return false;
      return true;
    });
  }

  function refreshGrid() {
    if (!gridEl) { render(); return; }
    while (gridEl.firstChild) gridEl.removeChild(gridEl.firstChild);
    const wfs = _view.data.workflows;
    if (!Array.isArray(wfs)) return;
    const filtered = applyFilters(wfs);
    if (filtered.length === 0) gridEl.appendChild(renderLibraryEmpty(wfs.length === 0));
    else filtered.forEach((w) => gridEl.appendChild(renderWorkflowCard(w)));
  }

  function renderLibraryEmpty(noWorkflowsAtAll) {
    return el("div", { class: "comfymodal-studio-workflows-empty" }, [
      el("p", { text: noWorkflowsAtAll
        ? "No workflows yet. Import the current ComfyUI graph or create a new empty workflow."
        : "No workflows match your filters." }),
      noWorkflowsAtAll ? null : el("button", {
        class: "comfymodal-secondary-btn",
        text: "Clear filters",
        onclick: () => { _view.filters = { query: "", tag: "", folder: "", favoritesOnly: false }; render(); },
      }),
    ]);
  }

  function renderWorkflowCard(w) {
    const wf = w || {};
    const id = wf.workflow_id || "";
    const state = wf.latest_version_state || null;
    const card = el("div", {
      class: "comfymodal-studio-workflow-card",
      "data-testid": "workflow-card",
      "data-workflow-id": id,
      tabindex: "0",
      role: "button",
      "aria-label": "Open workflow " + (wf.name || ""),
      onclick: () => openWorkflowDetail(id, wf.latest_version_id || "", null),
      onkeydown: (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openWorkflowDetail(id, wf.latest_version_id || "", null);
        }
      },
    }, [
      el("div", { class: "comfymodal-studio-workflow-card-top" }, [
        el("h3", { class: "comfymodal-studio-workflow-card-name", text: wf.name || "Untitled workflow" }),
        renderFavoriteButton(wf, true),
      ]),
      wf.folder ? el("div", { class: "comfymodal-studio-workflow-card-folder", text: wf.folder }) : null,
      (wf.tags && wf.tags.length)
        ? el("div", { class: "comfymodal-studio-workflows-tags" }, wf.tags.map((t) => _chip(String(t))))
        : null,
      el("div", { class: "comfymodal-studio-workflow-card-meta" }, [
        _stateBadge(state, "workflow-card-state"),
        el("span", { text: "v" + (wf.latest_version_number != null ? wf.latest_version_number : "0") }),
        wf.default_preset_name ? el("span", { text: wf.default_preset_name }) : null,
      ]),
      (wf.source_url || wf.source_author)
        ? el("div", { class: "comfymodal-studio-workflow-card-source", text: [wf.source_author, wf.source_url].filter(Boolean).join(" \u00b7 ") })
        : null,
    ]);
    return card;
  }

  function renderFavoriteButton(wf, isCard) {
    const props = {
      type: "button",
      class: "comfymodal-studio-favorite-star",
      "aria-label": wf.favorite ? "Remove from favorites" : "Add to favorites",
      "aria-pressed": wf.favorite ? "true" : "false",
      title: wf.favorite ? "Remove from favorites" : "Add to favorites",
      text: wf.favorite ? "\u2605" : "\u2606",
    };
    if (!isCard) props["data-testid"] = "workflow-detail-favorite";
    const star = el("button", props);
    star.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      if (star.disabled) return;
      const next = !wf.favorite;
      star.disabled = true;
      updateWorkflow(apiBase, wf.workflow_id, { favorite: next }).then((res) => {
        if (stale()) return;
        star.disabled = false;
        if (!res || res.status === "error") return;
        wf.favorite = next;
        star.textContent = next ? "\u2605" : "\u2606";
        star.setAttribute("aria-pressed", next ? "true" : "false");
        star.setAttribute("aria-label", next ? "Remove from favorites" : "Add to favorites");
        if (!isCard && _view.data.workflow) _view.data.workflow.favorite = next;
      });
    });
    return star;
  }

  function renderFolderTree() {
    const tree = _folderTree(_view.data.folders);
    const container = el("div", { class: "comfymodal-studio-workflows-folder-tree", "data-testid": "workflows-folder-tree" });
    container.appendChild(el("button", {
      type: "button",
      class: "comfymodal-studio-workflows-folder-item" + (!_view.filters.folder ? " active" : ""),
      text: "All folders",
      onclick: () => { _view.filters.folder = ""; render(); },
    }));
    appendFolderNodes(container, tree.children, 0);
    return container;
  }

  function appendFolderNodes(container, children, depth) {
    const names = Object.keys(children || {}).sort((a, b) => a.localeCompare(b));
    names.forEach((name) => {
      const node = children[name];
      const path = node.path;
      container.appendChild(el("button", {
        type: "button",
        class: "comfymodal-studio-workflows-folder-item" + (_view.filters.folder === path ? " active" : ""),
        text: name,
        style: "padding-left:" + (8 + depth * 14) + "px;",
        onclick: () => { _view.filters.folder = _view.filters.folder === path ? "" : path; render(); },
      }));
      appendFolderNodes(container, node.children, depth + 1);
    });
  }

  function renderLibraryView() {
    const viewEl = el("div", { class: "comfymodal-studio-workflows-view" });
    const wfs = _view.data.workflows;
    const filtered = Array.isArray(wfs) ? applyFilters(wfs) : null;

    // Sub-nav: Workflows library / Model Library sub-view.
    viewEl.appendChild(el("div", { class: "comfymodal-studio-subnav" }, [
      el("button", {
        class: "comfymodal-studio-subnav-btn" + (_view.mode === "library" ? " active" : ""),
        "data-testid": "wf-subnav-library",
        text: "Workflows",
        onclick: () => { _view.mode = "library"; render(); },
      }),
      el("button", {
        class: "comfymodal-studio-subnav-btn" + (_view.mode === "models" ? " active" : ""),
        "data-testid": "wf-subnav-models",
        text: "Model Library",
        onclick: () => { _view.mode = "models"; render(); },
      }),
    ]));

    viewEl.appendChild(el("div", { class: "comfymodal-studio-workflows-header" }, [
      el("div", { class: "comfymodal-studio-workflows-header-left" }, [
        el("h2", { class: "comfymodal-studio-workflows-title", text: "Workflows" }),
        Array.isArray(wfs)
          ? el("span", { class: "comfymodal-studio-workflows-count", text: wfs.length + (wfs.length === 1 ? " workflow" : " workflows") })
          : null,
      ]),
      el("div", { class: "comfymodal-studio-workflows-header-actions" }, [
        el("button", {
          class: "comfymodal-secondary-btn",
          "data-testid": "workflows-import-button",
          text: "Import",
          onclick: () => openImportDialog("graph"),
        }),
        el("button", {
          class: "comfymodal-primary-btn",
          "data-testid": "workflows-new-button",
          text: "New Workflow",
          style: "width:auto;padding:6px 14px;",
          onclick: () => openImportDialog("manual"),
        }),
      ]),
    ]));

    const searchInput = el("input", {
      type: "search",
      class: "comfymodal-studio-workflows-search",
      "data-testid": "workflows-search",
      "aria-label": "Search workflows",
      placeholder: "Search workflows\u2026",
      value: _view.filters.query,
      oninput: (e) => {
        const value = e.currentTarget.value;
        if (_searchTimer) clearTimeout(_searchTimer);
        _searchTimer = setTimeout(() => {
          _view.filters.query = value;
          refreshGrid();
        }, 250);
      },
    });

    const tagSelect = el("select", {
      class: "comfymodal-studio-workflows-select",
      "data-testid": "workflows-tag-filter",
      "aria-label": "Filter by tag",
      onchange: (e) => { _view.filters.tag = e.currentTarget.value; render(); },
    }, [
      el("option", { value: "", text: "All tags" }),
    ]);
    _view.data.tags.forEach((t) => tagSelect.appendChild(el("option", { value: t, text: t })));
    tagSelect.value = _view.filters.tag || "";

    const favToggle = el("button", {
      type: "button",
      class: "comfymodal-studio-workflows-toggle",
      "data-testid": "workflows-favorites-only",
      "aria-pressed": _view.filters.favoritesOnly ? "true" : "false",
      text: "Favorites only",
      onclick: () => {
        _view.filters.favoritesOnly = !_view.filters.favoritesOnly;
        favToggle.setAttribute("aria-pressed", _view.filters.favoritesOnly ? "true" : "false");
        refreshGrid();
      },
    });

    viewEl.appendChild(el("div", { class: "comfymodal-studio-workflows-toolbar" }, [searchInput, tagSelect, favToggle]));

    const sidebar = el("div", { class: "comfymodal-studio-workflows-sidebar" }, [
      el("div", { class: "comfymodal-studio-workflows-sidebar-label", text: "Folders" }),
      renderFolderTree(),
    ]);

    gridEl = el("div", { class: "comfymodal-studio-workflows-grid" });
    if (!Array.isArray(wfs)) {
      gridEl.appendChild(el("div", { class: "comfymodal-studio-workflows-empty", text: "Loading workflows\u2026" }));
    } else if (_view.data.loadError) {
      gridEl.appendChild(el("div", { class: "comfymodal-studio-workflows-empty" }, [
        el("p", { text: _view.data.loadError, style: "color:#f87171;" }),
        el("button", { class: "comfymodal-secondary-btn", text: "Retry", onclick: () => loadLibrary() }),
      ]));
    } else if (filtered.length === 0) {
      gridEl.appendChild(renderLibraryEmpty(wfs.length === 0));
    } else {
      filtered.forEach((w) => gridEl.appendChild(renderWorkflowCard(w)));
    }

    viewEl.appendChild(el("div", { class: "comfymodal-studio-workflows-body" }, [sidebar, gridEl]));

    if (_view.importMode) viewEl.appendChild(renderImportDialog());
    return viewEl;
  }

  async function loadLibrary() {
    render();
    const [wfResp, tagResp, folderResp] = await Promise.all([
      listWorkflows(apiBase, {}),
      listWorkflowTags(apiBase),
      listWorkflowFolders(apiBase),
    ]);
    if (stale()) return;
    const wfs = _unwrap(wfResp, "workflows");
    if (Array.isArray(wfs)) {
      _view.data.workflows = wfs;
      _view.data.loadError = null;
    } else {
      _view.data.loadError = "Could not load workflows from the server.";
    }
    const tags = _unwrap(tagResp, "tags");
    const tagSet = new Set(Array.isArray(tags) ? tags : []);
    if (Array.isArray(wfs)) wfs.forEach((w) => (w.tags || []).forEach((t) => tagSet.add(t)));
    _view.data.tags = Array.from(tagSet).sort();
    const folderPaths = [];
    _collectFolderPaths(_unwrap(folderResp, "folders"), "", folderPaths);
    _view.data.folders = Array.from(new Set(folderPaths)).sort();
    render();
  }

  // ── Import dialog ───────────────────────────────────────────────────────

  function openImportDialog(mode) {
    _view.importMode = mode || "graph";
    if (!_importEscHandler) {
      _importEscHandler = (e) => {
        if (e.key === "Escape" && _view.importMode) {
          e.stopPropagation();
          closeImportDialog();
        }
      };
      document.addEventListener("keydown", _importEscHandler, true);
    }
    render();
  }

  function closeImportDialog() {
    _view.importMode = "";
    if (_importEscHandler) {
      document.removeEventListener("keydown", _importEscHandler, true);
      _importEscHandler = null;
    }
    render();
  }

  function renderImportDialog() {
    const overlay = el("div", { class: "comfymodal-studio-dialog-overlay" });
    const backdrop = el("div", { class: "comfymodal-studio-dialog-backdrop", onclick: closeImportDialog });
    const dialog = el("div", {
      class: "comfymodal-studio-dialog",
      "data-testid": "import-dialog",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Import or create workflow",
    });

    dialog.appendChild(el("h3", { class: "comfymodal-studio-dialog-title", text: "Import / New Workflow" }));

    // Section 1: import from the current graph
    const graphNameInput = el("input", {
      type: "text",
      class: "comfymodal-studio-wf-input",
      placeholder: "Workflow name (optional \u2014 suggested from graph)",
    });
    const graphStatus = el("div", { class: "comfymodal-studio-dialog-status", style: "display:none;" });
    const importBtn = el("button", {
      class: "comfymodal-primary-btn",
      "data-testid": "import-confirm",
      text: "Import",
      style: "width:auto;",
      onclick: async () => {
        importBtn.disabled = true;
        try { await handleImportFromGraph(graphNameInput, graphStatus); }
        finally { importBtn.disabled = false; }
      },
    });
    dialog.appendChild(el("div", { class: "comfymodal-studio-dialog-section" }, [
      el("h4", { class: "comfymodal-studio-dialog-section-title", text: "Import from current ComfyUI graph" }),
      el("p", { class: "comfymodal-studio-dialog-note", text: "Captures the graph currently open in ComfyUI as the first version of a new workflow." }),
      graphNameInput,
      graphStatus,
      el("div", { class: "comfymodal-studio-dialog-actions" }, [importBtn]),
    ]));

    // Section 2: manual empty workflow
    const manualName = el("input", { type: "text", class: "comfymodal-studio-wf-input", placeholder: "Workflow name" });
    const manualFolder = el("input", { type: "text", class: "comfymodal-studio-wf-input", placeholder: "Folder (optional)" });
    const manualDesc = el("textarea", { class: "comfymodal-studio-textarea", rows: 2, placeholder: "Description (optional)" });
    const manualStatus = el("div", { class: "comfymodal-studio-dialog-status", style: "display:none;" });
    const createBtn = el("button", {
      class: "comfymodal-secondary-btn",
      text: "Create",
      onclick: async () => {
        createBtn.disabled = true;
        try { await handleManualCreate(manualName, manualFolder, manualDesc, manualStatus); }
        finally { createBtn.disabled = false; }
      },
    });
    dialog.appendChild(el("div", { class: "comfymodal-studio-dialog-section" }, [
      el("h4", { class: "comfymodal-studio-dialog-section-title", text: "New empty workflow" }),
      el("p", { class: "comfymodal-studio-dialog-note", text: "Creates an empty workflow with no version yet. Capture a version from the detail page." }),
      manualName,
      manualFolder,
      manualDesc,
      manualStatus,
      el("div", { class: "comfymodal-studio-dialog-actions" }, [createBtn]),
    ]));

    dialog.appendChild(el("div", { class: "comfymodal-studio-dialog-actions" }, [
      el("button", { class: "comfymodal-secondary-btn", text: "Cancel", onclick: closeImportDialog }),
    ]));

    overlay.appendChild(backdrop);
    overlay.appendChild(dialog);
    return overlay;
  }

  async function handleImportFromGraph(nameInput, statusEl) {
    _showStatus(statusEl, "Capturing current graph\u2026", false);
    const { captureCurrentComfyGraph } = await import("./studio-backend-capture.js");
    const capture = await captureCurrentComfyGraph();
    if (stale()) return;
    if (!capture || !capture.ok) {
      _showStatus(statusEl, (capture && capture.reason) || "Could not capture the current ComfyUI graph.", true);
      return;
    }
    (capture.warnings || []).forEach((w) => {
      statusEl.appendChild(el("div", { class: "comfymodal-studio-dialog-warning", text: w }));
    });
    const name = (nameInput.value || "").trim() || _suggestNameFromGraph(capture.graphJson);
    _showStatus(statusEl, "Importing workflow\u2026", false);
    const result = await importWorkflow(apiBase, {
      name: name,
      graph_json: capture.graphJson,
      api_prompt_json: capture.apiPromptJson,
    });
    if (stale()) return;
    if (!result || result.status === "error") {
      _showStatus(statusEl, "Import failed: " + _errorText(result), true);
      return;
    }
    const workflow = result.workflow || result;
    const wfId = workflow.workflow_id || result.workflow_id || "";
    const verId = workflow.latest_version_id
      || (result.version && result.version.workflow_version_id)
      || result.workflow_version_id
      || "";
    // Surface a dependency summary before closing the dialog so the user
    // knows the imported version needs attention (review on the detail page).
    const depSummary = result.dependency_summary && result.dependency_summary.summary;
    if (depSummary && (depSummary.attention || 0) > 0) {
      const n = depSummary.attention;
      _showStatus(
        statusEl,
        "Imported. " + n + " dependenc" + (n === 1 ? "y" : "ies")
          + (n === 1 ? " needs" : " need")
          + " attention \u2014 review on the workflow detail page.",
        false
      );
      await new Promise((r) => setTimeout(r, 1200));
      if (stale()) return;
    }
    closeImportDialog();
    openWorkflowDetail(wfId, verId, "Version created");
  }

  async function handleManualCreate(nameInput, folderInput, descInput, statusEl) {
    const name = (nameInput.value || "").trim();
    if (!name) {
      _showStatus(statusEl, "Enter a workflow name.", true);
      return;
    }
    _showStatus(statusEl, "Creating workflow\u2026", false);
    const result = await createWorkflow(apiBase, {
      name: name,
      folder: (folderInput.value || "").trim(),
      description: descInput.value || "",
    });
    if (stale()) return;
    if (!result || result.status === "error") {
      _showStatus(statusEl, "Could not create workflow: " + _errorText(result), true);
      return;
    }
    const workflow = result.workflow || result;
    closeImportDialog();
    openWorkflowDetail(workflow.workflow_id || result.workflow_id || "", "", null);
  }

  // ── Detail data loading ─────────────────────────────────────────────────

  async function loadDetailData() {
    const wfId = _view.selectedWorkflowId;
    if (!wfId) return;
    render();
    const [wfResp, verResp] = await Promise.all([
      getWorkflow(apiBase, wfId),
      listWorkflowVersions(apiBase, wfId),
    ]);
    if (stale()) return;
    const workflow = _unwrap(wfResp, "workflow");
    const versions = _unwrap(verResp, "versions");
    if (workflow && workflow.workflow_id) {
      _view.data.workflow = workflow;
      _view.data.loadError = null;
    } else {
      _view.data.loadError = "Could not load this workflow.";
    }
    _view.data.versions = Array.isArray(versions) ? versions : [];
    const valid = _view.data.versions.find((v) => v.workflow_version_id === _view.selectedVersionId);
    if (!valid) {
      const latest = _view.data.versions.find((v) => v.workflow_version_id === (workflow && workflow.latest_version_id))
        || _view.data.versions[_view.data.versions.length - 1]
        || null;
      _view.selectedVersionId = latest ? latest.workflow_version_id : "";
    }
    render();
    if (_view.selectedVersionId) await loadVersionData();
  }

  async function loadVersionData() {
    const verId = _view.selectedVersionId;
    if (!verId) return;
    const [verResp, preResp, mapResp, depResp] = await Promise.all([
      getWorkflowVersion(apiBase, verId),
      listVersionPresets(apiBase, verId),
      getMapping(apiBase, verId),
      getVersionDependencies(apiBase, verId),
    ]);
    if (stale()) return;
    const version = _unwrap(verResp, "version");
    if (version && version.workflow_version_id) {
      _view.data.version = version;
      _view.data.mappingVersionId = verId;
    }
    const presets = _unwrap(preResp, "presets");
    _view.data.presets = Array.isArray(presets) ? presets : [];
    const mapData = _unwrap(mapResp, "mapping");
    _view.data.mapping = mapData && mapData.mapping_id ? mapData : null;
    if (_view.data.mapping) _view.data.mappingVersionId = verId;
    // Dependencies payload has top-level models/custom_nodes/summary (no
    // wrapper key). Keep null on failure — the section shows a fallback note.
    _view.data.dependencies = depResp && depResp.status === "ok" ? depResp : null;
    render();
  }

  function selectVersion(versionId) {
    if (_view.selectedVersionId === versionId) return;
    _view.selectedVersionId = versionId;
    _view.editorMode = "";
    _view.activePresetId = "";
    _view.detailEditing = false;
    _view.revisionConfirm = false;
    _view.data.editPreset = null;
    _view.data.copyResults = null;
    _view.data.presetIncomplete = null;
    _view.data.version = null;
    _view.data.presets = [];
    _view.data.mapping = null;
    _view.data.dependencies = null;
    render();
    loadVersionData();
  }

  async function captureNewVersion() {
    if (_view.capturingVersion) return;
    _view.capturingVersion = true;
    render();
    const { captureCurrentComfyGraph } = await import("./studio-backend-capture.js");
    const capture = await captureCurrentComfyGraph();
    if (stale()) return;
    if (!capture || !capture.ok) {
      _view.capturingVersion = false;
      _view.data.notice = { text: (capture && capture.reason) || "Could not capture the current ComfyUI graph.", error: true };
      render();
      return;
    }
    const result = await captureWorkflowVersion(apiBase, _view.selectedWorkflowId, {
      graph_json: capture.graphJson,
      api_prompt_json: capture.apiPromptJson,
    });
    if (stale()) return;
    _view.capturingVersion = false;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not capture a new version: " + _errorText(result), error: true };
      render();
      return;
    }
    const newVerId = (result.version && result.version.workflow_version_id)
      || result.workflow_version_id
      || result.version_id
      || "";
    _view.data.notice = { text: "Version captured", error: false };
    const verResp = await listWorkflowVersions(apiBase, _view.selectedWorkflowId);
    if (stale()) return;
    const versions = _unwrap(verResp, "versions");
    _view.data.versions = Array.isArray(versions) ? versions : [];
    if (newVerId) _view.selectedVersionId = newVerId;
    else if (_view.data.versions.length) _view.selectedVersionId = _view.data.versions[_view.data.versions.length - 1].workflow_version_id;
    render();
    await loadVersionData();
  }

  // ── Detail view ─────────────────────────────────────────────────────────

  function renderNotice() {
    const n = _view.data.notice;
    if (!n) return null;
    return el("div", { class: "comfymodal-studio-notice" + (n.error ? " error" : "") }, [
      el("span", { text: n.text }),
      el("button", {
        type: "button",
        class: "comfymodal-studio-notice-dismiss",
        text: "\u00d7",
        "aria-label": "Dismiss",
        onclick: () => { _view.data.notice = null; render(); },
      }),
    ]);
  }

  function renderDetailView() {
    const wrap = el("div", { class: "comfymodal-studio-workflow-detail", "data-testid": "workflow-detail" });
    const wf = _view.data.workflow;
    const version = _view.data.version;
    const presets = _view.data.presets || [];
    const mapping = _view.data.mapping;

    wrap.appendChild(el("div", { class: "comfymodal-studio-detail-top" }, [
      el("button", { class: "comfymodal-secondary-btn", text: "\u2190 Back to Workflows", onclick: goToLibrary }),
    ]));

    if (_view.data.loadError && !wf) {
      wrap.appendChild(el("div", { class: "comfymodal-studio-card" }, [
        el("p", { text: _view.data.loadError, style: "color:#f87171;font-weight:600;margin:0 0 8px;" }),
        el("button", { class: "comfymodal-secondary-btn", text: "Retry", onclick: () => loadDetailData() }),
      ]));
      return wrap;
    }

    if (!wf) {
      wrap.appendChild(el("div", { class: "comfymodal-studio-workflows-empty", text: "Loading workflow\u2026" }));
      return wrap;
    }

    if (_view.data.notice) wrap.appendChild(renderNotice());
    wrap.appendChild(renderDetailHeader(wf));
    wrap.appendChild(renderRunBar(version, presets, mapping));
    wrap.appendChild(renderVersionsSection(wf));
    if (version) wrap.appendChild(renderDependenciesSection(version));
    wrap.appendChild(renderMappingSection(wf, version));
    wrap.appendChild(renderPresetsSection(wf, version, presets));
    if (_view.data.copyResults) wrap.appendChild(renderCopyResults());
    return wrap;
  }

  function renderDetailHeader(wf) {
    const card = el("div", { class: "comfymodal-studio-workflow-detail-header" });
    card.appendChild(el("div", { class: "comfymodal-studio-workflow-detail-title-row" }, [
      el("h1", { class: "comfymodal-studio-workflow-detail-title", "data-testid": "workflow-detail-name", text: wf.name || "Untitled workflow" }),
      renderFavoriteButton(wf, false),
      el("button", {
        class: "comfymodal-secondary-btn",
        text: _view.detailEditing ? "Cancel" : "Edit",
        onclick: () => { _view.detailEditing = !_view.detailEditing; render(); },
      }),
    ]));

    if (_view.detailEditing) {
      card.appendChild(renderDetailEditForm(wf));
      return card;
    }

    card.appendChild(el("div", { class: "comfymodal-studio-workflow-detail-meta" }, [
      el("span", { "data-testid": "workflow-detail-folder", text: wf.folder || "No folder" }),
      wf.updated_at ? el("span", { text: "Updated " + _shortDate(wf.updated_at) }) : null,
    ]));

    if (wf.description) {
      card.appendChild(el("p", { class: "comfymodal-studio-workflow-detail-desc", text: wf.description }));
    }

    // Tags row is always present so the add-tag control is reachable.
    card.appendChild(el("div", { class: "comfymodal-studio-workflow-detail-tags", "data-testid": "workflow-detail-tags" }, [
      el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Tags" }),
      ...(wf.tags || []).map((t) => renderTagChip(wf, t)),
      renderTagAdd(wf),
    ]));

    if (wf.source_url || wf.source_author) {
      const srcParts = [];
      if (wf.source_author) srcParts.push(el("span", { text: wf.source_author }));
      if (wf.source_url) srcParts.push(el("a", {
        class: "comfymodal-studio-workflows-link",
        href: wf.source_url,
        target: "_blank",
        rel: "noopener noreferrer",
        text: wf.source_url,
      }));
      card.appendChild(el("div", { class: "comfymodal-studio-workflow-detail-source", "data-testid": "workflow-detail-source" }, srcParts));
    }

    if (wf.compatible_models && wf.compatible_models.length) {
      card.appendChild(el("div", { class: "comfymodal-studio-workflows-tags" }, [
        el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Compatible models" }),
        ...wf.compatible_models.map((m) => _chip(String(m))),
      ]));
    }
    return card;
  }

  function renderTagChip(wf, tag) {
    return el("span", { class: "comfymodal-studio-wf-chip" }, [
      el("span", { text: tag }),
      el("button", {
        type: "button",
        class: "chip-x",
        text: "\u00d7",
        "aria-label": "Remove tag " + tag,
        onclick: (e) => {
          e.stopPropagation();
          const next = (wf.tags || []).filter((t) => t !== tag);
          updateWorkflow(apiBase, wf.workflow_id, { tags: next }).then((res) => {
            if (stale() || !res || res.status === "error") return;
            wf.tags = next;
            if (_view.data.workflow) _view.data.workflow.tags = next;
            render();
          });
        },
      }),
    ]);
  }

  function renderTagAdd(wf) {
    const input = el("input", {
      type: "text",
      class: "comfymodal-studio-wf-input comfymodal-studio-tag-add",
      placeholder: "Add tag",
      onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } },
    });
    function addTag() {
      const t = (input.value || "").trim();
      if (!t) return;
      const next = (wf.tags || []).concat([t]);
      updateWorkflow(apiBase, wf.workflow_id, { tags: next }).then((res) => {
        if (stale() || !res || res.status === "error") return;
        wf.tags = next;
        if (_view.data.workflow) _view.data.workflow.tags = next;
        input.value = "";
        render();
      });
    }
    return el("span", { class: "comfymodal-studio-tag-add-wrap" }, [
      input,
      el("button", { class: "comfymodal-secondary-btn", text: "Add", style: "padding:3px 8px;font-size:10px;", onclick: addTag }),
    ]);
  }

  function renderDetailEditForm(wf) {
    const values = {
      name: wf.name || "",
      description: wf.description || "",
      folder: wf.folder || "",
      source_url: wf.source_url || "",
      source_author: wf.source_author || "",
    };
    const form = el("div", { class: "comfymodal-studio-detail-edit-form" });
    const nameIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: values.name, oninput: (e) => { values.name = e.currentTarget.value; } });
    const descIn = el("textarea", { class: "comfymodal-studio-textarea", rows: 2, value: values.description, oninput: (e) => { values.description = e.currentTarget.value; } });
    const folderIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: values.folder, oninput: (e) => { values.folder = e.currentTarget.value; } });
    const urlIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: values.source_url, oninput: (e) => { values.source_url = e.currentTarget.value; } });
    const authorIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: values.source_author, oninput: (e) => { values.source_author = e.currentTarget.value; } });

    form.appendChild(_field("Name", nameIn));
    form.appendChild(_field("Description", descIn));
    form.appendChild(_field("Folder", folderIn));
    form.appendChild(_field("Source URL", urlIn));
    form.appendChild(_field("Source author", authorIn));
    form.appendChild(el("div", { class: "comfymodal-studio-backend-actions" }, [
      el("button", {
        class: "comfymodal-primary-btn",
        text: "Save",
        style: "width:auto;padding:6px 16px;",
        onclick: async () => {
          const res = await updateWorkflow(apiBase, wf.workflow_id, {
            name: values.name,
            description: values.description,
            folder: values.folder,
            source_url: values.source_url,
            source_author: values.source_author,
          });
          if (stale()) return;
          if (!res || res.status === "error") {
            _view.data.notice = { text: "Could not save workflow: " + _errorText(res), error: true };
            render();
            return;
          }
          const updated = res.workflow || null;
          if (updated && updated.workflow_id) _view.data.workflow = updated;
          else {
            wf.name = values.name; wf.description = values.description;
            wf.folder = values.folder; wf.source_url = values.source_url; wf.source_author = values.source_author;
          }
          _view.detailEditing = false;
          _view.data.notice = { text: "Workflow saved", error: false };
          render();
        },
      }),
      el("button", { class: "comfymodal-secondary-btn", text: "Cancel", onclick: () => { _view.detailEditing = false; render(); } }),
    ]));
    return form;
  }

  function renderRunBar(version, presets, mapping) {
    const bar = el("div", { class: "comfymodal-studio-run-bar" });
    const info = el("div", { class: "comfymodal-studio-run-bar-info" });
    let enabled = false;
    const reasons = [];
    if (!version) {
      info.appendChild(el("span", { class: "comfymodal-studio-run-bar-hint", text: "Loading selected version\u2026" }));
    } else {
      const runnable = !!(version.state && version.state.runnable === true);
      const hasPresets = (presets || []).length > 0;
      const hasMapping = !!mapping;
      if (!runnable) {
        (version.state && Array.isArray(version.state.reasons) ? version.state.reasons : [])
          .forEach((r) => reasons.push(_reasonText(r)));
      }
      if (runnable && !hasPresets && !hasMapping) {
        reasons.push("No preset or mapping on this version. Set up a mapping and create a preset to run it.");
      }
      enabled = runnable && (hasPresets || hasMapping);
      info.appendChild(el("span", {
        class: "comfymodal-studio-run-bar-version",
        text: "Version " + (version.version_number != null ? version.version_number : ""),
      }));
      if (enabled) {
        info.appendChild(el("span", { class: "comfymodal-studio-run-bar-hint", text: "Opens the Playground with this version's controls." }));
      } else if (reasons.length) {
        info.appendChild(_reasonList(reasons));
      }
    }
    bar.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      "data-testid": "run-button",
      text: "Run",
      disabled: !enabled,
      onclick: () => {
        // Hand off the selected workflow/version/preset to the Playground.
        // The preset is the version's default when determinable, else ""
        // (the Playground picks the version's default preset itself).
        const handoffPresetId =
          (version && version.default_preset_id)
          || ((presets || []).find((p) => p.is_default) || {}).preset_id
          || "";
        import("./studio-workflow-run.js").then((wf) => {
          wf.saveWorkflowHandoff({
            workflowId: version && version.workflow_id,
            workflowVersionId: version && version.workflow_version_id,
            presetId: handoffPresetId,
          });
          setPage("playground");
        }).catch(() => {
          // Handoff persistence is best-effort; navigate regardless.
          setPage("playground");
        });
      },
    }));
    bar.appendChild(info);
    return bar;
  }

  function renderVersionsSection(wf) {
    const versions = _view.data.versions || [];
    const section = el("div", { class: "comfymodal-studio-section" });
    section.appendChild(el("div", { class: "comfymodal-studio-section-head" }, [
      el("h3", { class: "comfymodal-studio-section-title", text: "Versions (" + versions.length + ")" }),
      el("button", {
        class: "comfymodal-secondary-btn",
        "data-testid": "version-capture-button",
        text: _view.capturingVersion ? "Capturing\u2026" : "Capture new version",
        disabled: !!_view.capturingVersion,
        onclick: captureNewVersion,
      }),
    ]));

    const list = el("div", { class: "comfymodal-studio-version-list", "data-testid": "version-list" });
    if (versions.length === 0) {
      list.appendChild(el("p", { class: "comfymodal-studio-dependencies-note", text: "No versions yet. Capture the current ComfyUI graph to create the first version." }));
    } else {
      versions.slice().sort((a, b) => (a.version_number || 0) - (b.version_number || 0)).forEach((v) => {
        list.appendChild(renderVersionItem(v));
      });
    }
    section.appendChild(list);
    return section;
  }

  function renderVersionItem(v) {
    const active = v.workflow_version_id === _view.selectedVersionId;
    const state = v.state || null;
    const incomplete = state && state.status === "incomplete";
    const reasons = incomplete && Array.isArray(state.reasons) ? state.reasons : [];
    const expanded = expandedVersions.has(v.workflow_version_id);
    const vnum = v.version_number != null ? v.version_number : "?";

    const main = el("div", { class: "comfymodal-studio-version-item-main" }, [
      el("span", { class: "comfymodal-studio-version-number", text: "v" + vnum }),
      _stateBadge(state, "version-item-state"),
      el("span", { class: "comfymodal-studio-version-sub", text: _shortDate(v.created_at) }),
      v.graph_hash ? el("span", { class: "comfymodal-studio-version-sub", text: _shortHash(v.graph_hash) }) : null,
      el("span", { class: "comfymodal-studio-version-sub", text: v.mapping_id ? "Mapped" : "Not mapped" }),
      el("span", { class: "comfymodal-studio-version-sub", text: (v.preset_count != null ? v.preset_count : 0) + " preset" + (v.preset_count === 1 ? "" : "s") }),
    ]);
    if (incomplete) {
      main.appendChild(el("button", {
        type: "button",
        class: "comfymodal-studio-version-reasons-toggle",
        text: expanded ? "Hide reasons" : "Show reasons",
        onclick: (e) => {
          e.stopPropagation();
          if (expanded) expandedVersions.delete(v.workflow_version_id);
          else expandedVersions.add(v.workflow_version_id);
          render();
        },
      }));
    }

    const item = el("div", {
      class: "comfymodal-studio-version-item" + (active ? " active" : ""),
      "data-testid": "version-item",
      "data-version-id": v.workflow_version_id,
      role: "button",
      tabindex: "0",
      "aria-label": "Select version " + vnum,
      onclick: () => selectVersion(v.workflow_version_id),
      onkeydown: (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectVersion(v.workflow_version_id);
        }
      },
    }, [main]);

    if (expanded) {
      item.appendChild(el("div", { class: "comfymodal-studio-version-reasons" }, [
        _reasonList(reasons),
      ]));
    }
    return item;
  }

  function renderDependenciesSection(version) {
    // Thin wrapper: the section body lives in studio-model-library.js; the
    // Refresh button re-fetches the dependencies endpoint for this version.
    return renderDependencySection(version, _view.data.dependencies, refreshDependencies);
  }

  async function refreshDependencies() {
    const verId = _view.selectedVersionId;
    if (!verId) return;
    const resp = await getVersionDependencies(apiBase, verId);
    if (stale()) return;
    _view.data.dependencies = resp && resp.status === "ok" ? resp : null;
    render();
  }

  // ── Mapping section ─────────────────────────────────────────────────────

  function renderMappingSection(wf, version) {
    const hasMapping = !!_view.data.mapping;
    const section = el("div", { class: "comfymodal-studio-section", "data-testid": "mapping-editor" });
    section.appendChild(el("div", { class: "comfymodal-studio-section-head" }, [
      el("h3", { class: "comfymodal-studio-section-title", text: "Mapping" }),
      _view.editorMode === "mapping" ? el("button", {
        class: "comfymodal-secondary-btn",
        text: "Close",
        onclick: () => { _view.editorMode = ""; _view.revisionConfirm = false; render(); },
      }) : null,
    ]));

    if (_view.editorMode === "mapping") {
      section.appendChild(renderMappingEditor(wf, version, hasMapping));
    } else if (hasMapping) {
      const m = _view.data.mapping;
      const count = (m.entries || []).length;
      section.appendChild(el("div", { class: "comfymodal-studio-mapping-summary" }, [
        el("div", { class: "comfymodal-studio-mapping-summary-row" }, [
          el("span", { class: "comfymodal-studio-role-info", text: count + " mapped control" + (count === 1 ? "" : "s") }),
          m.output_node_id ? el("span", { class: "comfymodal-studio-role-info", text: "Output node: " + m.output_node_id }) : null,
          el("span", { class: "comfymodal-studio-role-info", text: "Edits create a new immutable version" }),
        ]),
        el("button", {
          class: "comfymodal-secondary-btn",
          text: "Edit mapping",
          onclick: () => { _view.editorMode = "mapping"; render(); ensureMappingEditorData(); },
        }),
      ]));
    } else {
      section.appendChild(el("div", { class: "comfymodal-studio-mapping-summary" }, [
        el("p", { class: "comfymodal-studio-dependencies-note", text: "This version has no mapping. Set up a mapping to expose its controls." }),
        el("button", {
          class: "comfymodal-primary-btn",
          text: "Set up Mapping",
          style: "width:auto;",
          onclick: () => { _view.editorMode = "mapping"; render(); ensureMappingEditorData(); },
        }),
      ]));
    }
    return section;
  }

  function renderMappingEditor(wf, version, hasMapping) {
    const container = el("div", { class: "comfymodal-studio-mapping-editor" });

    // Version state + reasons at the top of the editor.
    const state = (version && version.state) || null;
    if (state) {
      container.appendChild(el("div", { class: "comfymodal-studio-mapping-state" }, [
        _stateBadge(state, null),
        (state.reasons && state.reasons.length)
          ? _reasonList(state.reasons)
          : el("span", { class: "comfymodal-studio-role-hint", text: "Version state is ready." }),
      ]));
    }

    const entries = hasMapping
      ? ((_view.data.mapping && _view.data.mapping.entries) || [])
      : ((_view.data.candidates && _view.data.candidates.entries) || []);

    if (!hasMapping && !_view.data.candidates) {
      container.appendChild(el("p", { class: "comfymodal-studio-dependencies-note", text: "Loading mapping candidates\u2026" }));
      return container;
    }

    mappingControls = {};
    const candWrap = el("div", { class: "comfymodal-studio-mapping-candidates", "data-testid": "mapping-candidates" });
    if (entries.length === 0) {
      candWrap.appendChild(el("p", { class: "comfymodal-studio-dependencies-note", text: "No candidate controls were found in this version's graph." }));
    } else {
      entries.forEach((entry) => candWrap.appendChild(renderMappingRoleRow(entry, hasMapping)));
    }
    container.appendChild(candWrap);

    const outputNodeId = hasMapping
      ? (_view.data.mapping && _view.data.mapping.output_node_id)
      : (_view.data.candidates && _view.data.candidates.output_node_id);
    if (outputNodeId) {
      container.appendChild(el("p", { class: "comfymodal-studio-role-hint", text: "Output node: " + outputNodeId }));
    }

    if (hasMapping) {
      // Mapped version → the save action is explicitly a REVISION.
      container.appendChild(el("button", {
        class: "comfymodal-primary-btn",
        "data-testid": "mapping-revision-button",
        text: "Save as New Workflow Version",
        style: "width:auto;align-self:flex-start;",
        onclick: () => { _view.revisionConfirm = !_view.revisionConfirm; render(); },
      }));
      if (_view.revisionConfirm) {
        container.appendChild(el("div", { class: "comfymodal-studio-confirm-panel" }, [
          el("p", { text: "Workflow Versions are immutable. Saving changes creates a NEW version; this version and its presets stay untouched.", style: "margin:0;" }),
          el("div", { class: "comfymodal-studio-dialog-actions", style: "justify-content:flex-start;" }, [
            el("button", {
              class: "comfymodal-primary-btn",
              "data-testid": "mapping-revision-confirm",
              text: "Create New Version",
              style: "width:auto;",
              onclick: saveMappingRevision,
            }),
            el("button", {
              class: "comfymodal-secondary-btn",
              text: "Cancel",
              onclick: () => { _view.revisionConfirm = false; render(); },
            }),
          ]),
        ]));
      }
    } else {
      container.appendChild(el("button", {
        class: "comfymodal-primary-btn",
        "data-testid": "mapping-save",
        text: "Save Mapping",
        style: "width:auto;align-self:flex-start;",
        onclick: saveMapping,
      }));
    }
    return container;
  }

  function renderMappingRoleRow(entry, hasMapping) {
    const kind = _controlKind(entry);
    let value = hasMapping
      ? entry.value
      : (entry.default !== undefined ? entry.default : undefined);
    if (kind === "node" && value == null) value = entry.node_id;
    const control = _makeControl(entry, value);
    mappingControls[entry.semantic_role || entry.input_name] = control;

    const row = el("div", { class: "comfymodal-studio-mapping-role-row", "data-testid": "mapping-role-row" });
    row.appendChild(el("div", { class: "comfymodal-studio-mapping-role-head" }, [
      el("span", { class: "comfymodal-studio-role-label", text: _roleName(entry) }),
      entry.required ? el("span", { class: "comfymodal-studio-role-required", text: "Required" }) : null,
      el("span", { class: "comfymodal-studio-role-info", text: _roleInfo(entry) }),
    ]));
    row.appendChild(control);
    const hint = _numHint(entry);
    if (hint) row.appendChild(el("span", { class: "comfymodal-studio-role-hint", text: hint }));
    if (kind === "file" || kind === "image") {
      row.appendChild(el("span", { class: "comfymodal-studio-role-hint", text: "Path or URL" }));
    }
    return row;
  }

  async function ensureMappingEditorData() {
    const verId = _view.selectedVersionId;
    if (!verId) return;
    if (_view.data.candidatesVersionId === verId && _view.data.candidates) return;
    _view.data.candidates = null;
    const resp = await getMappingCandidates(apiBase, verId);
    if (stale()) return;
    const cand = resp && resp.candidates ? resp.candidates : resp;
    _view.data.candidates = {
      entries: cand && Array.isArray(cand.entries) ? cand.entries : [],
      output_node_id: cand ? cand.output_node_id : null,
    };
    _view.data.candidatesVersionId = verId;
    render();
  }

  function collectMappingEntries(hasMapping) {
    const src = hasMapping
      ? ((_view.data.mapping && _view.data.mapping.entries) || [])
      : ((_view.data.candidates && _view.data.candidates.entries) || []);
    return src.map((entry) => {
      const key = entry.semantic_role || entry.input_name;
      const ctrl = mappingControls[key];
      const copy = Object.assign({}, entry);
      if (ctrl) copy.value = _readControlValue(entry, ctrl);
      return copy;
    });
  }

  async function saveMapping() {
    if (!_view.data.candidates) return;
    const entries = collectMappingEntries(false);
    const result = await createMapping(apiBase, _view.selectedVersionId, {
      entries: entries,
      output_node_id: _view.data.candidates.output_node_id || null,
    });
    if (stale()) return;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not save mapping: " + _errorText(result), error: true };
      render();
      return;
    }
    _view.editorMode = "";
    _view.data.notice = { text: "Mapping saved", error: false };
    await loadVersionData();
    render();
  }

  async function saveMappingRevision() {
    const entries = collectMappingEntries(true);
    const result = await createMappingRevision(apiBase, _view.selectedVersionId, {
      entries: entries,
      output_node_id: (_view.data.mapping && _view.data.mapping.output_node_id) || null,
    });
    if (stale()) return;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not create the new version: " + _errorText(result), error: true };
      render();
      return;
    }
    const newVerId = (result.version && result.version.workflow_version_id)
      || result.workflow_version_id
      || result.version_id
      || "";
    _view.editorMode = "";
    _view.revisionConfirm = false;
    _view.data.notice = { text: "New workflow version created", error: false };
    const verResp = await listWorkflowVersions(apiBase, _view.selectedWorkflowId);
    if (stale()) return;
    const versions = _unwrap(verResp, "versions");
    _view.data.versions = Array.isArray(versions) ? versions : [];
    if (newVerId) _view.selectedVersionId = newVerId;
    render();
    await loadVersionData();
  }

  // ── Presets section ─────────────────────────────────────────────────────

  function openPresetEditor(preset) {
    _view.editorMode = "preset";
    _view.activePresetId = preset ? preset.preset_id : "";
    _view.data.editPreset = preset || null;
    _view.data.presetIncomplete = null;
    render();
    ensurePresetEditorData();
  }

  function renderPresetsSection(wf, version, presets) {
    const section = el("div", { class: "comfymodal-studio-section" });
    const latestId = wf.latest_version_id;
    const hasNewer = !!latestId && !!_view.selectedVersionId && latestId !== _view.selectedVersionId;
    const presetIds = (presets || []).map((p) => p.preset_id).filter(Boolean);

    section.appendChild(el("div", { class: "comfymodal-studio-section-head" }, [
      el("h3", { class: "comfymodal-studio-section-title", text: "Presets" }),
      el("div", { class: "comfymodal-studio-workflows-header-actions" }, [
        hasNewer && presetIds.length ? el("button", {
          class: "comfymodal-secondary-btn",
          "data-testid": "preset-bulk-copy-button",
          text: "Copy all to latest",
          onclick: bulkCopyToLatest,
        }) : null,
        el("button", {
          class: "comfymodal-primary-btn",
          text: "New Preset",
          style: "width:auto;padding:6px 14px;",
          onclick: () => openPresetEditor(null),
        }),
      ]),
    ]));

    const list = el("div", { class: "comfymodal-studio-preset-list", "data-testid": "preset-list" });
    if (presets.length === 0) {
      list.appendChild(el("p", { class: "comfymodal-studio-dependencies-note", text: "No presets for this version yet. Create one to store control values." }));
    } else {
      presets.forEach((p) => list.appendChild(renderPresetCard(wf, p, hasNewer, latestId)));
    }
    section.appendChild(list);

    if (_view.editorMode === "preset") {
      section.appendChild(renderPresetEditor(wf, version, presets));
    }
    return section;
  }

  function renderPresetCard(wf, p, hasNewer, latestId) {
    const state = p.state || null;
    const reasons = (state && Array.isArray(state.reasons)) ? state.reasons : [];
    const card = el("div", {
      class: "comfymodal-studio-wf-preset-card" + (p.is_default ? " is-default" : ""),
      "data-testid": "preset-card",
      "data-preset-id": p.preset_id,
    }, [
      el("div", { class: "comfymodal-studio-wf-preset-card-top" }, [
        el("span", { class: "comfymodal-studio-wf-preset-card-name", "data-testid": "preset-card-name", text: p.name || "Unnamed preset" }),
        p.is_default ? el("span", { class: "comfymodal-studio-wf-chip default", text: "Default" }) : null,
        _stateBadge(state, "preset-card-state"),
      ]),
      p.description ? el("p", { class: "comfymodal-studio-wf-preset-card-desc", text: p.description }) : null,
      reasons.length ? _reasonList(reasons) : null,
      (p.tags && p.tags.length)
        ? el("div", { class: "comfymodal-studio-workflows-tags" }, p.tags.map((t) => _chip(String(t))))
        : null,
      el("div", { class: "comfymodal-studio-wf-preset-card-actions" }, [
        el("button", {
          class: "comfymodal-secondary-btn",
          "data-testid": "preset-default-button",
          text: p.is_default ? "Clear default" : "Set as default",
          onclick: () => toggleDefaultPreset(p),
        }),
        el("button", { class: "comfymodal-secondary-btn", "data-testid": "preset-duplicate-button", text: "Duplicate", onclick: () => duplicatePresetAction(p) }),
        el("button", { class: "comfymodal-secondary-btn", "data-testid": "preset-edit-button", text: "Edit", onclick: () => openPresetEditor(p) }),
        hasNewer && latestId ? el("button", {
          class: "comfymodal-secondary-btn",
          "data-testid": "preset-copy-button",
          text: "Copy to latest",
          onclick: () => copyPresetToLatest(p, latestId),
        }) : null,
        el("button", {
          class: "comfymodal-destructive-btn",
          text: "Delete",
          style: "font-size:10px;padding:4px 10px;",
          onclick: () => deletePresetAction(p),
        }),
      ]),
    ]);
    return card;
  }

  async function toggleDefaultPreset(p) {
    const wf = _view.data.workflow;
    if (!wf) return;
    const result = p.is_default
      ? await clearWorkflowDefaultPreset(apiBase, wf.workflow_id)
      : await setWorkflowDefaultPreset(apiBase, wf.workflow_id, p.preset_id);
    if (stale()) return;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not update default preset: " + _errorText(result), error: true };
      render();
      return;
    }
    await loadVersionData();
    render();
  }

  async function duplicatePresetAction(p) {
    const result = await duplicateWorkflowPreset(apiBase, p.preset_id);
    if (stale()) return;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not duplicate preset: " + _errorText(result), error: true };
      render();
      return;
    }
    _view.data.notice = { text: "Preset duplicated", error: false };
    await loadVersionData();
    render();
  }

  async function deletePresetAction(p) {
    const result = await deleteWorkflowPreset(apiBase, p.preset_id);
    if (stale()) return;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not delete preset: " + _errorText(result), error: true };
      render();
      return;
    }
    _view.data.notice = { text: "Preset deleted", error: false };
    await loadVersionData();
    render();
  }

  async function copyPresetToLatest(p, latestId) {
    const result = await copyPresetToVersion(apiBase, p.preset_id, latestId);
    if (stale()) return;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not copy preset: " + _errorText(result), error: true };
      render();
      return;
    }
    _view.data.copyResults = [result];
    render();
  }

  async function bulkCopyToLatest() {
    const wf = _view.data.workflow;
    if (!wf || !wf.latest_version_id) return;
    const presetIds = (_view.data.presets || []).map((p) => p.preset_id).filter(Boolean);
    if (!presetIds.length) return;
    const result = await bulkCopyPresetsToVersion(apiBase, _view.selectedVersionId, presetIds);
    if (stale()) return;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not copy presets: " + _errorText(result), error: true };
      render();
      return;
    }
    let results = (result && (result.results || result.copy_results || result.items)) || [];
    if (!results.length && result && result.preset) results = [result];
    _view.data.copyResults = results.length ? results : null;
    render();
  }

  function renderCopyResults() {
    const results = _view.data.copyResults || [];
    const section = el("div", { class: "comfymodal-studio-section copy-results-section" });
    section.appendChild(el("div", { class: "comfymodal-studio-section-head" }, [
      el("h3", { class: "comfymodal-studio-section-title", text: "Copy results" }),
      el("button", { class: "comfymodal-secondary-btn", text: "Dismiss", onclick: () => { _view.data.copyResults = null; render(); } }),
    ]));
    section.appendChild(el("div", { class: "comfymodal-studio-copy-results", "data-testid": "copy-results" },
      results.map((r) => renderCopyResultItem(r))));
    return section;
  }

  function renderCopyResultItem(r) {
    const state = r.state || {};
    const runnable = state.runnable === true;
    const reasons = (state.reasons || []).map(_reasonText);
    const dropped = (r.dropped_controls || [])
      .map(_reasonText)
      .filter((x) => reasons.indexOf(x) === -1);
    const name = (r.preset && r.preset.name) || "Preset";
    const item = el("div", {
      class: "comfymodal-studio-copy-result-item " + (runnable ? "ok" : "warn"),
      "data-testid": "copy-result-item",
    }, [
      el("div", { class: "comfymodal-studio-copy-result-name", text: runnable ? name + " \u2014 Copied" : name + " \u2014 Copied but incomplete" }),
    ]);
    if (!runnable && reasons.length) item.appendChild(_reasonList(reasons));
    if (dropped.length) {
      item.appendChild(el("ul", { class: "comfymodal-studio-reason-list dropped" },
        dropped.map((x) => el("li", { text: "Dropped mapped control: " + x }))));
    }
    return item;
  }

  // ── Preset editor ───────────────────────────────────────────────────────

  async function ensurePresetEditorData() {
    const verId = _view.selectedVersionId;
    if (!verId) return;
    if (_view.data.mappingVersionId !== verId) {
      const mapResp = await getMapping(apiBase, verId);
      if (stale()) return;
      const mapData = _unwrap(mapResp, "mapping");
      _view.data.mapping = mapData && mapData.mapping_id ? mapData : null;
      _view.data.mappingVersionId = verId;
    }
    if (_view.activePresetId && (!_view.data.editPreset || _view.data.editPreset.preset_id !== _view.activePresetId)) {
      const pResp = await getWorkflowPreset(apiBase, _view.activePresetId);
      if (stale()) return;
      const preset = _unwrap(pResp, "preset");
      _view.data.editPreset = preset && preset.preset_id ? preset : null;
    }
    render();
  }

  // Lazily fetch the model library once per editor session for the preset
  // "Model choices" pickers. On failure the editor falls back to text inputs.
  async function ensureModelsCache() {
    if (_view.modelsCacheState === "loading") return;
    _view.modelsCacheState = "loading";
    const resp = await listModels(apiBase, {});
    if (stale()) return;
    if (resp && resp.status === "ok" && Array.isArray(resp.models)) {
      _view.modelsCache = resp.models;
      _view.modelsCacheState = "loaded";
    } else {
      _view.modelsCache = null;
      _view.modelsCacheState = "failed";
    }
    render();
  }

  function renderPresetEditor(wf, version, presets) {
    const container = el("div", { class: "comfymodal-studio-section preset-editor-section", "data-testid": "preset-editor" });
    const editPreset = _view.data.editPreset;
    const isEdit = !!editPreset;
    const mapping = _view.data.mapping;
    presetEntries = (mapping && Array.isArray(mapping.entries)) ? mapping.entries : [];
    presetRefs = { values: {}, rec: {}, models: {}, exposed: {}, loraRows: [] };

    container.appendChild(el("div", { class: "comfymodal-studio-section-head" }, [
      el("h3", { class: "comfymodal-studio-section-title", text: isEdit ? "Edit Preset" : "New Preset" }),
      el("button", {
        class: "comfymodal-secondary-btn",
        text: "Close",
        onclick: () => {
          _view.editorMode = "";
          _view.activePresetId = "";
          _view.data.editPreset = null;
          _view.data.presetIncomplete = null;
          render();
        },
      }),
    ]));

    // Incomplete state from the last save — shown instead of claiming success.
    if (_view.data.presetIncomplete) {
      container.appendChild(el("div", { class: "comfymodal-studio-confirm-panel incomplete", "data-testid": "preset-state-reasons" }, [
        el("p", { text: "Preset was saved but is incomplete:", style: "margin:0;" }),
        el("ul", { class: "comfymodal-studio-reason-list" },
          _view.data.presetIncomplete.reasons.map((r) => el("li", { text: _reasonText(r) }))),
      ]));
    }

    if (presetEntries.length === 0) {
      container.appendChild(el("p", { class: "comfymodal-studio-dependencies-note", text: "This version has no mapping yet. Set up a mapping first so preset controls can be defined." }));
    }

    const editor = el("div", { class: "comfymodal-studio-preset-editor" });

    // Basic fields
    const nameIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", "data-testid": "preset-name-input", value: (editPreset && editPreset.name) || "" });
    presetRefs.name = nameIn;
    const descIn = el("textarea", { class: "comfymodal-studio-textarea", rows: 2, value: (editPreset && editPreset.description) || "" });
    presetRefs.description = descIn;
    const tagsIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: ((editPreset && editPreset.tags) || []).join(", ") });
    presetRefs.tags = tagsIn;
    const favIn = el("input", { type: "checkbox", class: "comfymodal-studio-wf-checkbox" });
    favIn.checked = !!(editPreset && editPreset.favorite);
    presetRefs.favorite = favIn;

    editor.appendChild(_editorBlock("Details", el("div", { class: "comfymodal-studio-editor-grid" }, [
      _field("Name", nameIn),
      _field("Description", descIn),
      _field("Tags (comma separated)", tagsIn),
      el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Favorite" }), favIn]),
    ])));

    // Values from mapping entries
    if (presetEntries.length) {
      const pv = (editPreset && editPreset.values) || {};
      const grid = el("div", { class: "comfymodal-studio-editor-grid" });
      presetEntries.forEach((entry) => {
        const role = entry.semantic_role || entry.input_name;
        const value = pv[role] !== undefined
          ? pv[role]
          : (entry.value !== undefined ? entry.value : (entry.default !== undefined ? entry.default : undefined));
        const ctrl = _makeControl(entry, value);
        presetRefs.values[role] = ctrl;
        const wrap = el("div", { class: "comfymodal-studio-backend-field" }, [
          el("label", { text: _roleName(entry) + (entry.required ? " *" : "") }),
          ctrl,
        ]);
        const hint = _numHint(entry);
        if (hint) wrap.appendChild(el("span", { class: "comfymodal-studio-role-hint", text: hint }));
        grid.appendChild(wrap);
      });
      editor.appendChild(_editorBlock("Values", grid));
    }

    // Model choices — library dropdowns for model-kind roles. Falls back to
    // plain text inputs when the model library cannot be fetched.
    const modelEntries = presetEntries.filter((e) => e.kind === "model");
    if (modelEntries.length) {
      const mc = (editPreset && editPreset.model_choices) || {};
      const compatibleModels = (version && Array.isArray(version.compatible_models))
        ? version.compatible_models
        : [];
      const grid = el("div", { class: "comfymodal-studio-editor-grid" });
      modelEntries.forEach((entry) => {
        const role = entry.semantic_role || entry.input_name;
        const currentValue = mc[role] !== undefined ? String(mc[role]) : "";
        let ctrl;
        if (_view.modelsCacheState === "failed") {
          ctrl = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: currentValue });
        } else {
          ctrl = renderModelPicker({
            compatibleModels,
            currentValue,
            models: _view.modelsCache || [],
            onSelect: () => { /* selection is read from select.value */ },
          });
        }
        presetRefs.models[role] = ctrl;
        grid.appendChild(_field("Model \u00b7 " + _roleName(entry), ctrl));
      });
      editor.appendChild(_editorBlock("Model choices", grid));
      if (_view.modelsCacheState !== "loaded" && _view.modelsCacheState !== "failed") {
        ensureModelsCache();
      }
    }

    // LoRA values — free-form key/value rows
    const loraBlock = el("div", { class: "comfymodal-studio-editor-block" });
    loraBlock.appendChild(el("h4", { class: "comfymodal-studio-editor-block-title", text: "LoRA values" }));
    const loraRowsWrap = el("div", { class: "comfymodal-studio-lora-rows" });
    const lv = (editPreset && editPreset.lora_values) || {};
    const loraPairs = Object.keys(lv).map((k) => ({ name: k, weight: lv[k] }));
    if (!loraPairs.length) loraPairs.push({ name: "", weight: "" });
    loraPairs.forEach((pair) => loraRowsWrap.appendChild(_loraRow(pair)));
    loraBlock.appendChild(loraRowsWrap);
    loraBlock.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: "Add LoRA",
      style: "align-self:flex-start;",
      onclick: () => { loraRowsWrap.appendChild(_loraRow({ name: "", weight: "" })); },
    }));
    editor.appendChild(loraBlock);

    // Recommended values — editable per entry
    if (presetEntries.length) {
      const rec = (editPreset && editPreset.recommended_values) || {};
      const grid = el("div", { class: "comfymodal-studio-editor-grid" });
      presetEntries.forEach((entry) => {
        const role = entry.semantic_role || entry.input_name;
        const value = rec[role] !== undefined ? rec[role] : (entry.value !== undefined ? entry.value : undefined);
        const ctrl = _makeControl(entry, value);
        presetRefs.rec[role] = ctrl;
        grid.appendChild(_field("Recommended \u00b7 " + _roleName(entry), ctrl));
      });
      editor.appendChild(_editorBlock("Recommended values", grid));
    }

    // Exposed controls — checkboxes per role
    if (presetEntries.length) {
      const exp = (editPreset && editPreset.exposed_controls) || [];
      const grid = el("div", { class: "comfymodal-studio-editor-grid" });
      presetEntries.forEach((entry) => {
        const role = entry.semantic_role || entry.input_name;
        const cb = el("input", { type: "checkbox", class: "comfymodal-studio-wf-checkbox" });
        cb.checked = exp.indexOf(role) !== -1;
        presetRefs.exposed[role] = cb;
        grid.appendChild(el("div", { class: "comfymodal-studio-backend-field" }, [
          el("label", { text: _roleName(entry) }),
          cb,
        ]));
      });
      editor.appendChild(_editorBlock("Exposed controls", grid));
    }

    editor.appendChild(el("div", { class: "comfymodal-studio-backend-actions" }, [
      el("button", { class: "comfymodal-primary-btn", "data-testid": "preset-save", text: "Save", style: "width:auto;padding:7px 18px;", onclick: onSavePreset }),
      el("button", {
        class: "comfymodal-secondary-btn",
        text: "Cancel",
        onclick: () => {
          _view.editorMode = "";
          _view.activePresetId = "";
          _view.data.editPreset = null;
          _view.data.presetIncomplete = null;
          render();
        },
      }),
    ]));

    container.appendChild(editor);
    return container;
  }

  function _editorBlock(title, content) {
    return el("div", { class: "comfymodal-studio-editor-block" }, [
      el("h4", { class: "comfymodal-studio-editor-block-title", text: title }),
      content,
    ]);
  }

  function _loraRow(pair) {
    const nameIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", placeholder: "LoRA name", value: pair.name || "" });
    const weightIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", placeholder: "Weight", value: pair.weight != null ? String(pair.weight) : "" });
    const row = el("div", { class: "comfymodal-studio-lora-row" }, [
      nameIn,
      weightIn,
      el("button", {
        type: "button",
        class: "comfymodal-destructive-btn",
        text: "Remove",
        style: "font-size:10px;padding:4px 8px;",
        onclick: () => row.remove(),
      }),
    ]);
    presetRefs.loraRows.push({ name: nameIn, weight: weightIn });
    return row;
  }

  function _entryByRole(role) {
    return (presetEntries || []).find((e) => (e.semantic_role || e.input_name) === role) || {};
  }

  function buildPresetPayload() {
    const name = (presetRefs.name && (presetRefs.name.value || "").trim()) || "";
    const description = presetRefs.description ? presetRefs.description.value : "";
    const tags = (presetRefs.tags && (presetRefs.tags.value || "")).split(",").map((t) => t.trim()).filter(Boolean);
    const favorite = presetRefs.favorite ? presetRefs.favorite.checked : false;

    const values = {};
    Object.keys(presetRefs.values).forEach((role) => {
      values[role] = _readControlValue(_entryByRole(role), presetRefs.values[role]);
    });

    const recommended_values = {};
    Object.keys(presetRefs.rec).forEach((role) => {
      recommended_values[role] = _readControlValue(_entryByRole(role), presetRefs.rec[role]);
    });

    const model_choices = {};
    Object.keys(presetRefs.models).forEach((role) => {
      model_choices[role] = presetRefs.models[role].value || "";
    });

    const lora_values = {};
    presetRefs.loraRows.forEach((row) => {
      const n = (row.name.value || "").trim();
      if (!n) return;
      const w = row.weight.value.trim();
      lora_values[n] = w === "" ? "" : w;
    });

    const exposed_controls = [];
    Object.keys(presetRefs.exposed).forEach((role) => {
      if (presetRefs.exposed[role].checked) exposed_controls.push(role);
    });

    return {
      name: name,
      description: description,
      tags: tags,
      favorite: favorite,
      values: values,
      model_choices: model_choices,
      lora_values: lora_values,
      recommended_values: recommended_values,
      exposed_controls: exposed_controls,
    };
  }

  async function onSavePreset() {
    const name = (presetRefs.name && (presetRefs.name.value || "").trim()) || "";
    if (!name) {
      _view.data.presetIncomplete = { reasons: ["Enter a preset name."] };
      render();
      return;
    }
    const payload = buildPresetPayload();
    const isEdit = !!_view.data.editPreset;
    const result = isEdit
      ? await updateWorkflowPreset(apiBase, _view.activePresetId, payload)
      : await createVersionPreset(apiBase, _view.selectedVersionId, payload);
    if (stale()) return;
    if (!result || result.status === "error") {
      _view.data.notice = { text: "Could not save preset: " + _errorText(result), error: true };
      render();
      return;
    }
    const preset = result.preset || null;
    if (preset && preset.state && preset.state.status === "incomplete") {
      _view.data.presetIncomplete = { reasons: preset.state.reasons || [] };
      render();
      return;
    }
    _view.editorMode = "";
    _view.activePresetId = "";
    _view.data.editPreset = null;
    _view.data.presetIncomplete = null;
    _view.data.notice = { text: "Preset saved", error: false };
    await loadVersionData();
    render();
  }

  // ── Mount ───────────────────────────────────────────────────────────────

  render();
  if (_view.mode === "detail") loadDetailData();
  else loadLibrary();

  return root;
}
