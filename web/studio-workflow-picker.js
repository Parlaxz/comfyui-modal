// Modal Studio — Shared Workflow Picker (Studio Workflow effort, leaf 1.2.1)
//
// Single shared folder/search picker for workflows. Single-run callers use
// mode "single" (select-one); experiment callers use mode "many"
// (select-many). Folder/search list behavior lives ONLY here — callers
// supply their own mode-specific actions, never a second picker UI.
//
// The picker uses the shared short-lived workflow list cache (unfiltered) and
// narrows it locally on every keystroke/selection. This keeps the dialog on
// the exact list URL the library already uses — no per-keystroke query-string
// list requests — so search/folder narrowing behaves identically against the
// real backend and test doubles.
//
// Role display names come from the verified bindable-input catalog
// (web/studio-bindable-inputs.js). This module must not duplicate it.
// Backend/Preset concepts stay out: the picker deals in workflow ids only,
// no migration, no second authority.
//
// Render contract: renderWorkflowPicker(options) → DOM node.
//   options — {
//     apiBase,                 // "/comfymodal" default
//     mode,                    // "single" (default) | "many"
//     workflowType,            // optional tool filter ("t2i", "i2i", …,
//                             // aliases accepted); when set the list shows
//                             // only workflows of that type
//     workflowTypes,           // optional array alternative to workflowType
//     selectedIds,             // initially selected workflow ids
//     requiredRoles,           // optional role keys, labelled via the catalog
//     confirmLabel,            // confirm button text (default per mode)
//     actions,                 // caller-supplied mode actions:
//                             // [{ label, testid, onAction(ids) }] — rendered
//                             // beside confirm, enabled only with a selection
//     onSelect,                // onSelect(ids) on every selection change
//     onConfirm,               // onConfirm(ids) on confirm
//   }

import { el } from "./studio-ui.js";
import { listWorkflows, listWorkflowFolders } from "./studio-backend-api.js";
import { BINDABLE_INPUTS, normalizeWorkflowType } from "./studio-bindable-inputs.js";

// Empty-list requests are shared by the library, picker, and run flow.  Keep
// the cache deliberately short-lived: it removes duplicate navigation fetches
// without turning the browser into a second inventory authority.
const WORKFLOW_LIST_CACHE_TTL_MS = 20_000;
const _workflowListCache = new Map();
const _workflowListInFlight = new Map();

export function listCachedWorkflows(apiBase) {
  const key = apiBase || "/comfymodal";
  const now = Date.now();
  const cached = _workflowListCache.get(key);
  if (cached && now - cached.at < WORKFLOW_LIST_CACHE_TTL_MS) {
    return Promise.resolve(cached.response);
  }

  const pending = _workflowListInFlight.get(key);
  if (pending) return pending;

  const request = listWorkflows(key, {}).then((response) => {
    if (response && response.status !== "error") {
      _workflowListCache.set(key, { at: Date.now(), response });
    }
    return response;
  }).finally(() => {
    if (_workflowListInFlight.get(key) === request) _workflowListInFlight.delete(key);
  });
  _workflowListInFlight.set(key, request);
  return request;
}

export function invalidateCachedWorkflows(apiBase) {
  const key = apiBase || "/comfymodal";
  _workflowListCache.delete(key);
}

// Catalog-owned role name. Unknown keys fall back to the raw key — never a
// second hardcoded name table.
export function roleDisplayName(roleKey) {
  const entry = roleKey && BINDABLE_INPUTS[roleKey];
  return entry ? entry.name : String(roleKey || "");
}

export function roleDisplayNames(roleKeys) {
  return (roleKeys || []).map(roleDisplayName);
}

function _unwrapList(resp, key) {
  if (!resp) return [];
  if (Array.isArray(resp)) return resp;
  if (typeof resp === "object") {
    if (resp.status === "error") return [];
    if (Array.isArray(resp[key])) return resp[key];
  }
  return [];
}

function _folderNames(folders) {
  const out = [];
  (folders || []).forEach((f) => {
    if (f == null) return;
    if (typeof f === "string") {
      if (f) out.push(f);
    } else if (typeof f === "object") {
      const name = f.path || f.name || f.label || "";
      if (name) out.push(String(name));
    }
  });
  return out;
}

export function renderWorkflowPicker(options) {
  const opts = options || {};
  const apiBase = opts.apiBase || "/comfymodal";
  const mode = opts.mode === "many" ? "many" : "single";
  const selected = new Set((opts.selectedIds || []).map(String));
  const onSelect = typeof opts.onSelect === "function" ? opts.onSelect : null;
  const onConfirm = typeof opts.onConfirm === "function" ? opts.onConfirm : null;
  const actions = Array.isArray(opts.actions) ? opts.actions : [];
  const confirmLabel = opts.confirmLabel
    || (mode === "many" ? "Use selected workflows" : "Use workflow");

  // Optional tool scoping (e.g. the Text-to-Image tool passes "t2i" so the
  // dialog never offers image-edit/inpaint workflows). Absent/empty means
  // all types, preserving existing callers (library dialog, compare).
  const _wantedTypes = (function () {
    const raw = opts.workflowTypes !== undefined ? opts.workflowTypes : opts.workflowType;
    const list = Array.isArray(raw) ? raw : (raw ? [raw] : []);
    const set = new Set();
    list.forEach((t) => {
      const n = normalizeWorkflowType(t);
      if (n) set.add(n);
    });
    return set;
  })();

  function _rowType(w) {
    return normalizeWorkflowType((w && (w.workflow_type || w.workflowType || w.type)) || "t2i");
  }

  const root = el("div", {
    class: "comfymodal-studio-workflow-picker",
    "data-testid": "workflow-picker",
    "data-mode": mode,
  });

  if (Array.isArray(opts.requiredRoles) && opts.requiredRoles.length) {
    root.appendChild(el("p", {
      class: "comfymodal-studio-dialog-note",
      "data-testid": "workflow-picker-roles",
      text: "Needs: " + roleDisplayNames(opts.requiredRoles).join(", "),
    }));
  }

  const searchInput = el("input", {
    type: "search",
    class: "comfymodal-studio-workflows-search",
    "data-testid": "workflow-picker-search",
    "aria-label": "Search workflows",
    placeholder: "Search workflows\u2026",
  });

  const folderSelect = el("select", {
    class: "comfymodal-studio-workflows-select",
    "data-testid": "workflow-picker-folder",
    "aria-label": "Filter by folder",
  }, [el("option", { value: "", text: "All folders" })]);

  const listEl = el("div", {
    class: "comfymodal-studio-workflow-picker-list",
    "data-testid": "workflow-picker-list",
    role: mode === "many" ? "group" : "listbox",
    "aria-label": "Workflows",
  });

  const confirmBtn = el("button", {
    type: "button",
    class: "comfymodal-primary-btn",
    "data-testid": "workflow-picker-confirm",
    text: confirmLabel,
    style: "width:auto;",
    onclick: () => { if (onConfirm) onConfirm(Array.from(selected)); },
  });

  const actionBtns = actions.map((a) => el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    "data-testid": (a && a.testid) || "workflow-picker-action",
    text: (a && a.label) || "Action",
    onclick: () => { if (a && typeof a.onAction === "function") a.onAction(Array.from(selected)); },
  }));

  function syncButtons() {
    const empty = selected.size === 0;
    confirmBtn.disabled = empty;
    actionBtns.forEach((b) => { b.disabled = empty; });
  }

  function emit() {
    syncButtons();
    if (onSelect) onSelect(Array.from(selected));
  }

  function renderOptions(workflows) {
    while (listEl.firstChild) listEl.removeChild(listEl.firstChild);
    if (!workflows.length) {
      listEl.appendChild(el("p", {
        class: "comfymodal-studio-dialog-note",
        "data-testid": "workflow-picker-empty",
        text: "No workflows match.",
      }));
      return;
    }
    workflows.forEach((w) => {
      const id = String((w && w.workflow_id) || "");
      if (!id) return;
      const isOn = selected.has(id);
      const opt = el("button", {
        type: "button",
        class: "comfymodal-studio-workflow-picker-option" + (isOn ? " active" : ""),
        "data-testid": "workflow-picker-option",
        "data-workflow-id": id,
        role: "option",
        "aria-selected": isOn ? "true" : "false",
        "aria-label": "Select workflow " + ((w && w.name) || id),
        onclick: () => {
          if (mode === "many") {
            if (selected.has(id)) selected.delete(id);
            else selected.add(id);
          } else {
            selected.clear();
            selected.add(id);
          }
          emit();
          renderOptions(workflows);
        },
      }, [
        el("span", { text: (w && w.name) || "Untitled workflow" }),
        w && w.folder ? el("span", {
          class: "comfymodal-studio-workflow-card-folder",
          text: w.folder,
        }) : null,
      ]);
      listEl.appendChild(opt);
    });
  }

  let searchTimer = null;
  let requestToken = 0;
  let allWorkflows = []; // full list from the single unfiltered fetch

  // Local narrowing over the cached full list: folder uses the same
  // exact-or-subfolder semantics as the backend/library; search matches
  // name + description + tags like the library's client-side filter; an
  // optional workflowType scopes the dialog to one tool's workflows.
  function applyFilter() {
    const q = (searchInput.value || "").trim().toLowerCase();
    const folder = folderSelect.value || "";
    const rows = allWorkflows.filter((w) => {
      if (_wantedTypes.size && !_wantedTypes.has(_rowType(w))) return false;
      if (folder) {
        const wf = String((w && w.folder) || "");
        if (!(wf === folder || wf.indexOf(folder + "/") === 0)) return false;
      }
      if (q) {
        const hay = [(w && w.name), (w && w.description), ((w && w.tags) || []).join(" ")]
          .filter(Boolean).join(" ").toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
    renderOptions(rows);
    syncButtons();
  }

  async function load() {
    const token = ++requestToken;
    listEl.textContent = "";
    listEl.appendChild(el("p", {
      class: "comfymodal-studio-dialog-note",
      "data-testid": "workflow-picker-loading",
      text: "Loading workflows\u2026",
    }));
    const resp = await listCachedWorkflows(apiBase);
    if (token !== requestToken) return;
    allWorkflows = _unwrapList(resp, "workflows");
    applyFilter();
    emit();
  }

  async function loadFolders() {
    const resp = await listWorkflowFolders(apiBase);
    _folderNames(_unwrapList(resp, "folders")).sort().forEach((name) => {
      folderSelect.appendChild(el("option", { value: name, text: name }));
    });
  }

  searchInput.addEventListener("input", () => {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilter, 250);
  });
  folderSelect.addEventListener("change", applyFilter);

  root.appendChild(el("div", {
    class: "comfymodal-studio-workflows-toolbar",
  }, [searchInput, folderSelect]));
  if (_wantedTypes.size) {
    const _typeLabels = { t2i: "Text to Image", i2i: "Image Edit", inpaint: "Inpaint", sketch: "Sketch", outpaint: "Outpaint" };
    const _names = Array.from(_wantedTypes).map((t) => _typeLabels[t] || t).join(", ");
    root.appendChild(el("p", {
      class: "comfymodal-studio-dialog-note",
      "data-testid": "workflow-picker-type-note",
      text: "Showing only " + _names + " workflows.",
    }));
  }
  root.appendChild(listEl);
  root.appendChild(el("div", {
    class: "comfymodal-studio-dialog-actions",
  }, [confirmBtn].concat(actionBtns)));

  syncButtons();
  loadFolders();
  load();

  return root;
}
