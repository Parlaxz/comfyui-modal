// Modal Studio — Model Library + Workflow Dependency System
//
// Renders the Model Library view (a sub-view of the Workflows page), the
// workflow-version dependency section, and the model picker used by the
// preset editor.  All DOM is built through el() from studio-ui.js.
//
// State contract: the workflows page owns a module-level `_view` object and
// passes it here as `view`.  Library state lives in `view.modelsData`
// ({ models, scanHint, filters, types, customNodes, loading, _loaded }), the
// preset-editor model cache lives in `view.modelsCache` /
// `view.modelsCacheState`.  `refresh` re-renders the whole workflows page.
//
// Authority: this view is read-only over the canonical stores —
// `.studio_model_library.json` (models) and `.studio_custom_nodes.json`
// (custom nodes) via the /studio/models* and /studio/custom-nodes* routes.
// Scans/refreshes run ONLY on explicit user action (never on render), and
// install requests only RECORD approval — nothing is ever downloaded or
// installed automatically.

import { el, renderEmptyState } from "./studio-ui.js";
import { renderLoadingState } from "./studio-loading.js";
import {
  listModels,
  listModelTypes,
  listCustomNodes,
  refreshCustomNodes,
  rescanModels,
  updateModel,
  requestModelInstall,
  requestCustomNodeInstall,
} from "./studio-backend-api.js";

// ── Module helpers ────────────────────────────────────────────────────────

// Folder bucket per model type, used by the "Request download" section.
const MODEL_BUCKETS = {
  checkpoint: "checkpoints",
  unet: "unet",
  clip: "clip/text_encoders",
  vae: "vae",
  lora: "loras",
  controlnet: "controlnet",
  upscaler: "upscale_models",
  other: "checkpoints",
};

let _searchTimer = null;

function _fmtSize(bytes) {
  if (bytes == null || Number.isNaN(Number(bytes))) return "";
  const n = Number(bytes);
  if (n <= 0) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2) + " " + units[i];
}

function _shortCommit(h) {
  if (!h) return "";
  const s = String(h);
  return s.length > 10 ? s.slice(0, 10) : s;
}

function _flattenStack(stack) {
  if (!stack) return [];
  if (Array.isArray(stack)) return stack.map(String);
  if (typeof stack === "object") {
    const out = [];
    for (const k of Object.keys(stack)) {
      const v = stack[k];
      if (Array.isArray(v)) v.forEach((x) => out.push(String(x)));
      else if (v != null && v !== "") out.push(String(v));
    }
    return out;
  }
  return [];
}

// Badge for library rows and dependency rows. I3 chip taxonomy: shared
// `.cm-chip` base + truthful tone while keeping the page-specific class.
// Truthful mapping: installed→ok, missing/wrong-version→warn (capability
// family), unknown/type/role→neutral (identity/unknown).
function _badge(text, kind) {
  const tone =
    kind === "installed" ? "ok"
      : (kind === "missing" || kind === "warning") ? "warn"
        : "neutral";
  return el("span", {
    class: "comfymodal-studio-model-badge " + kind + " cm-chip",
    "data-tone": tone,
    text: text,
  });
}

function _stateBadgeFor(state) {
  if (state === "installed") return _badge("Installed", "installed");
  if (state === "missing") return _badge("Missing", "missing");
  if (state === "wrong_version") return _badge("Wrong version", "warning");
  return _badge("Unknown", "unknown");
}

// ── Model Library view ────────────────────────────────────────────────────

/**
 * Render the Model Library sub-view.
 * @param {object} opts { apiBase, view, refresh } — view is the workflows
 *   module `_view`; refresh re-renders the workflows page.
 * @returns {HTMLElement}
 */
export function renderModelLibraryView(opts) {
  const { apiBase, view, refresh } = opts;
  const md = view.modelsData || (view.modelsData = {
    models: [],
    scanHint: "not_scanned",
    filters: { query: "", type: "", state: "" },
    types: [],
    customNodes: [],
    loading: false,
    _loaded: false,
  });

  // First open: kick off the initial data load.  A query set externally
  // (dependency-row handoff) after the first load re-fetches once.
  if (!md._loaded && !md.loading) {
    md.loading = true;
    loadModelsData(apiBase, view, refresh);
  } else if (md._queryDirty && !md.loading) {
    md._queryDirty = false;
    reloadModelsList(apiBase, view, refresh);
  }

  const root = el("div", { class: "comfymodal-studio-model-library", "data-testid": "models-page" });

  // ── Header row ──────────────────────────────────────────────────────────
  const scanBtn = el("button", {
    class: "comfymodal-primary-btn",
    "data-testid": "models-rescan",
    text: md.loading && !md._loaded ? "Scanning\u2026" : "Scan models",
    disabled: !!(md.loading && !md._loaded),
    style: "width:auto;padding:6px 14px;",
    onclick: () => handleRescan(apiBase, view, refresh, scanBtn, rehashCb),
  });
  const rehashCb = el("input", { type: "checkbox", class: "comfymodal-studio-wf-checkbox", title: "Force full rehash of every file" });
  root.appendChild(el("div", { class: "comfymodal-studio-model-library-header" }, [
    el("div", { class: "comfymodal-studio-model-library-header-left" }, [
      // I6 heading hierarchy: this sub-view replaces the library view's
      // content, so its title is the page-level h2 (under the single shell
      // h1), styled with the same page-title class as "Workflows".
      el("h2", { class: "comfymodal-studio-workflows-title", "data-testid": "models-page-title", text: "Model Library" }),
      el("span", { class: "comfymodal-studio-models-count", "data-testid": "models-count", text: md.models.length + " model" + (md.models.length === 1 ? "" : "s") }),
    ]),
    el("div", { class: "comfymodal-studio-workflows-header-actions" }, [
      el("button", {
        class: "comfymodal-secondary-btn",
        "data-testid": "models-back",
        text: "Workflows",
        onclick: () => {
          view.mode = "library";
          refresh();
        },
      }),
    ]),
  ]));

  root.appendChild(el("div", { class: "comfymodal-studio-model-library-header" }, [
    el("div", { class: "comfymodal-studio-models-toolbar" }, [
      scanBtn,
      el("label", { class: "comfymodal-studio-rehash-label" }, [rehashCb, el("span", { text: "Full rehash" })]),
    ]),
  ]));

  // Rescan summary line (shown transiently after a scan completes).
  const rescanStatus = el("div", { class: "comfymodal-studio-dialog-status", style: "display:none;" });
  root.appendChild(rescanStatus);
  // Latest rendered status element — the list reload after a scan re-renders
  // the page, so the handler writes its outcome to this fresh node.
  md._rescanStatusEl = rescanStatus;

  // ── Filters row ─────────────────────────────────────────────────────────
  const searchIn = el("input", {
    type: "search",
    class: "comfymodal-studio-workflows-search",
    "data-testid": "models-search",
    "aria-label": "Search models",
    placeholder: "Search models\u2026",
    value: md.filters.query,
    oninput: (e) => {
      const value = e.currentTarget.value;
      md._modelHighlight = ""; // manual edit invalidates handoff highlighting
      if (_searchTimer) clearTimeout(_searchTimer);
      _searchTimer = setTimeout(() => {
        md.filters.query = value;
        reloadModelsList(apiBase, view, refresh);
      }, 250);
    },
  });

  const typeSel = el("select", {
    class: "comfymodal-studio-workflows-select",
    "data-testid": "models-type-filter",
    "aria-label": "Filter by model type",
    onchange: (e) => {
      md.filters.type = e.currentTarget.value;
      reloadModelsList(apiBase, view, refresh);
    },
  }, [el("option", { value: "", text: "All types" })]);
  (md.types || []).forEach((t) => typeSel.appendChild(el("option", { value: t, text: t })));
  typeSel.value = md.filters.type || "";

  const stateSel = el("select", {
    class: "comfymodal-studio-workflows-select",
    "data-testid": "models-state-filter",
    "aria-label": "Filter by install state",
    onchange: (e) => {
      md.filters.state = e.currentTarget.value;
      reloadModelsList(apiBase, view, refresh);
    },
  }, [
    el("option", { value: "", text: "All states" }),
    el("option", { value: "installed", text: "Installed" }),
    el("option", { value: "missing", text: "Missing" }),
  ]);
  stateSel.value = md.filters.state || "";

  root.appendChild(el("div", { class: "comfymodal-studio-workflows-toolbar" }, [searchIn, typeSel, stateSel]));

  // ── Model list ──────────────────────────────────────────────────────────
  const list = el("div", { class: "comfymodal-studio-model-list", "data-testid": "models-list" });
  if (md.loading && !md._loaded) {
    list.appendChild(renderLoadingState({
      label: "Loading models\u2026",
      size: "page",
      testid: "models-loading",
    }));
  } else if (md.scanHint === "not_scanned" && md.models.length === 0) {
    list.appendChild(renderEmptyState({
      title: "No models scanned yet",
      detail: "Click Scan models to index the local model folders.",
      testid: "models-empty",
    }));
  } else if (md.models.length === 0) {
    list.appendChild(renderEmptyState({
      title: "No models match your filters",
      testid: "models-empty",
    }));
  } else {
    md.models.forEach((m) => list.appendChild(renderModelRow(m, apiBase, view, refresh)));
  }
  root.appendChild(list);

  // ── Custom nodes section ────────────────────────────────────────────────
  root.appendChild(renderCustomNodesSection(md, apiBase, refresh));

  return root;

  // ── Internal async handlers (closure-scoped) ────────────────────────────

  async function handleRescan(apiBaseRef, viewRef, refreshRef, btn, rehashInput) {
    if (btn.disabled) return; // request dedupe: ignore clicks while in flight
    btn.disabled = true;
    btn.textContent = "Scanning\u2026";
    let ok = false;
    let msg = "";
    const resp = await rescanModels(apiBaseRef, rehashInput.checked);
    const summary = resp && resp.summary ? resp.summary : null;
    const total = summary ? summary.total : null;
    if (resp && resp.status === "ok") {
      ok = true;
      msg = summary
        ? "Scan complete \u2014 " + total + " model" + (total === 1 ? "" : "s") + " total."
        : "Scan complete.";
    } else {
      msg = "Scan failed: " + ((resp && resp.message) || "request failed");
    }
    if (viewRef.modelsData) viewRef.modelsData.scanHint = "ok";
    btn.disabled = false;
    btn.textContent = "Scan models";
    await reloadModelsList(apiBaseRef, viewRef, refreshRef);
    const live = (viewRef.modelsData && viewRef.modelsData._rescanStatusEl) || null;
    if (live) {
      live.style.display = "block";
      live.textContent = msg;
      live.classList.toggle("error", !ok);
    }
  }
}

async function loadModelsData(apiBase, view, refresh) {
  const md = view.modelsData;
  md.loading = true;
  const [listResp, typesResp, nodesResp] = await Promise.all([
    listModels(apiBase, _modelQuery(md)),
    listModelTypes(apiBase),
    listCustomNodes(apiBase),
  ]);
  if (listResp && listResp.status === "ok" && Array.isArray(listResp.models)) {
    md.models = listResp.models;
  }
  if (listResp && listResp.scan_hint) md.scanHint = listResp.scan_hint;
  if (typesResp && typesResp.status === "ok" && Array.isArray(typesResp.types)) {
    md.types = typesResp.types;
  }
  if (nodesResp && nodesResp.status === "ok" && Array.isArray(nodesResp.custom_nodes)) {
    md.customNodes = nodesResp.custom_nodes;
  }
  md.loading = false;
  md._loaded = true;
  refresh();
}

async function reloadModelsList(apiBase, view, refresh) {
  const md = view.modelsData;
  md.loading = true;
  const resp = await listModels(apiBase, _modelQuery(md));
  if (resp && resp.status === "ok" && Array.isArray(resp.models)) {
    md.models = resp.models;
  }
  if (resp && resp.scan_hint) md.scanHint = resp.scan_hint;
  md.loading = false;
  refresh();
}

// Map the UI filter state ({query,type,state}) to the API option shape
// ({search,type,state}) — the client contract uses `search`, not `query`.
function _modelQuery(md) {
  const f = (md && md.filters) || {};
  return { search: f.query || "", type: f.type || "", state: f.state || "" };
}

// ── Custom nodes section (canonical registry browse + explicit refresh) ───

/**
 * Render the custom-node registry section of the Model Library view.
 * Read-only over `.studio_custom_nodes.json` via /studio/custom-nodes;
 * the refresh button is the ONLY trigger for POST /studio/custom-nodes/refresh.
 *
 * I6 "Find in registry" handoff: when `md._registryFocus` is set (dependency
 * row handoff), the section filters client-side by node name/class substring,
 * highlights an exact-name match, and offers an explicit Clear.  Navigation
 * only — nothing installs, refreshes, or fetches automatically.
 */
function renderCustomNodesSection(md, apiBase, refresh) {
  const nodes = Array.isArray(md.customNodes) ? md.customNodes : [];
  const focus = typeof md._registryFocus === "string" ? md._registryFocus.trim() : "";
  const focusQuery = focus.toLowerCase();
  const visible = focusQuery
    ? nodes.filter((n) => {
        const name = String((n && n.name) || "").toLowerCase();
        if (name.indexOf(focusQuery) !== -1) return true;
        const classes = Array.isArray(n && n.classes) ? n.classes : [];
        return classes.some((c) => String(c || "").toLowerCase().indexOf(focusQuery) !== -1);
      })
    : nodes;

  const section = el("div", {
    class: "comfymodal-studio-section",
    "data-testid": "custom-nodes-section",
  });

  const refreshBtn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "custom-nodes-refresh",
    text: "Refresh registry",
    style: "font-size:10px;padding:4px 10px;width:auto;",
    onclick: () => handleNodesRefresh(apiBase, md, refresh, refreshBtn, statusEl),
  });

  section.appendChild(el("div", { class: "comfymodal-studio-section-head" }, [
    el("h3", { class: "comfymodal-studio-section-title", text: "Custom nodes" }),
    el("span", {
      class: "comfymodal-studio-models-count",
      "data-testid": "custom-nodes-count",
      text: (focusQuery ? visible.length + " of " : "") +
        nodes.length + " installed node" + (nodes.length === 1 ? "" : "s"),
    }),
    refreshBtn,
  ]));

  if (focusQuery) {
    section.appendChild(el("div", {
      class: "comfymodal-studio-dependency-banner attention",
      "data-testid": "custom-nodes-focus",
    }, [
      el("span", {
        class: "comfymodal-studio-dependency-banner-label",
        text: "Registry filtered by \"" + focus + "\".",
      }),
      el("button", {
        class: "comfymodal-secondary-btn",
        type: "button",
        "data-testid": "custom-nodes-focus-clear",
        text: "Clear",
        style: "font-size:10px;padding:2px 8px;width:auto;",
        onclick: () => {
          md._registryFocus = "";
          refresh();
        },
      }),
    ]));
  }

  const statusEl = el("div", { class: "comfymodal-studio-dialog-status", style: "display:none;" });
  section.appendChild(statusEl);
  // Latest rendered status element — refresh() rebuilds the whole page, so
  // the async handler writes its outcome here instead of a detached node.
  md._nodesStatusEl = statusEl;

  const table = el("div", { class: "comfymodal-studio-dependency-table", "data-testid": "custom-nodes-list" });
  if (nodes.length === 0) {
    table.appendChild(el("p", {
      class: "comfymodal-studio-dependencies-note",
      text: "No custom nodes recorded yet. Use Refresh registry to rediscover installed nodes.",
    }));
  } else if (visible.length === 0) {
    table.appendChild(el("p", {
      class: "comfymodal-studio-dependencies-note",
      "data-testid": "custom-nodes-no-match",
      text: "No installed registry node matches \"" + focus + "\".",
    }));
  } else {
    visible.forEach((n) => table.appendChild(renderRegistryNodeRow(n, focusQuery)));
  }
  section.appendChild(table);
  return section;

  async function handleNodesRefresh(apiBaseRef, mdRef, refreshRef, btn, statusRef) {
    if (btn.disabled) return; // request dedupe: ignore clicks while in flight
    btn.disabled = true;
    btn.textContent = "Refreshing\u2026";
    let ok = false;
    let msg = "";
    try {
      const resp = await refreshCustomNodes(apiBaseRef);
      if (resp && resp.status === "ok" && Array.isArray(resp.custom_nodes)) {
        mdRef.customNodes = resp.custom_nodes;
        ok = true;
        msg = "Registry refreshed \u2014 " + resp.custom_nodes.length
          + " node" + (resp.custom_nodes.length === 1 ? "" : "s") + " found.";
      } else {
        msg = "Refresh failed: " + ((resp && resp.message) || "request failed");
      }
    } catch (err) {
      msg = "Refresh failed: " + (err && err.message ? err.message : "request failed");
    }
    btn.disabled = false;
    btn.textContent = "Refresh registry";
    refreshRef(); // synchronous re-render: list/count reflect the refresh result
    const live = mdRef._nodesStatusEl || statusRef;
    live.style.display = "block";
    live.textContent = msg;
    live.classList.toggle("error", !ok);
  }
}

// One row of the canonical custom-node registry (installed truth only).
// `focusQuery` (lowercased) highlights an exact-name match from the
// "Find in registry" handoff — inline style only, no shared-CSS change.
function renderRegistryNodeRow(n, focusQuery) {
  const name = String(n.name || "");
  const exactMatch = !!focusQuery && name.toLowerCase() === focusQuery;
  const row = el("div", {
    class: "comfymodal-studio-dependency-row",
    "data-testid": "custom-node-row",
    "data-node-name": name,
  });
  if (exactMatch) {
    row.setAttribute("data-registry-match", "true");
    row.style.cssText =
      "outline:1px solid var(--color-accent, #5a7fdb);outline-offset:-1px;" +
      "background:var(--color-accent-muted, rgba(90, 127, 219, 0.12));";
  }
  row.appendChild(el("span", { class: "comfymodal-studio-dependency-name", text: name, title: name }));
  row.appendChild(_badge("Installed", "installed"));
  row.appendChild(el("span", {
    class: "comfymodal-studio-dependency-detail",
    text: n.installed_commit ? _shortCommit(n.installed_commit) : "",
    title: n.installed_commit || "",
  }));
  const classes = Array.isArray(n.classes) ? n.classes : [];
  if (classes.length) {
    row.appendChild(el("span", {
      class: "comfymodal-studio-dependency-detail",
      text: classes.length + " class" + (classes.length === 1 ? "" : "es"),
      title: classes.join(", "),
    }));
  }
  if (n.install_path) {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-path", text: n.install_path, title: n.install_path }));
  }
  if (n.repo_url) {
    row.appendChild(el("a", { class: "comfymodal-studio-models-link", href: n.repo_url, target: "_blank", rel: "noopener noreferrer", text: "repo" }));
  }
  return row;
}

function renderModelRow(m, apiBase, view, refresh) {
  const row = el("div", {
    class: "comfymodal-studio-model-row",
    "data-testid": "model-row",
    "data-model-id": m.model_id,
  });
  const main = el("div", { class: "comfymodal-studio-model-main" }, [
    el("span", { class: "comfymodal-studio-model-name", text: m.display_name || m.filename || "" }),
    el("span", { class: "comfymodal-studio-model-file", text: m.filename || "" }),
  ]);
  // I6 reverse-usage line (session-derived): shown only when a dependency
  // payload fetched in this session referenced this model filename.  The
  // tooltip states that scope; View filters the Workflows list to those
  // workflows through the EXISTING library filter state — no new store.
  const usage = view && view.usageByModel instanceof Map
    ? view.usageByModel.get(m.filename)
    : null;
  if (usage && usage.size > 0) {
    main.appendChild(el("span", {
      class: "comfymodal-studio-model-used-by",
      "data-testid": "model-used-by",
      title: "From workflow dependencies loaded in this session.",
    }, [
      el("span", { text: "Used by " + usage.size + " workflow" + (usage.size === 1 ? "" : "s") + " \u00b7 " }),
      el("button", {
        class: "comfymodal-secondary-btn",
        type: "button",
        "data-testid": "model-used-by-view",
        text: "View",
        style: "font-size:10px;padding:1px 6px;width:auto;",
        onclick: () => {
          view.mode = "library";
          view.filters.usageModel = m.filename;
          refresh();
        },
      }),
    ]));
  }
  row.appendChild(main);
  // Exact-match highlight for the dependency-row "Find in library" handoff.
  if (view && typeof view.modelsData?._modelHighlight === "string" &&
      view.modelsData._modelHighlight !== "" &&
      String(m.filename) === view.modelsData._modelHighlight) {
    row.setAttribute("data-model-match", "true");
    row.style.cssText =
      "outline:1px solid var(--color-accent, #5a7fdb);outline-offset:-1px;";
  }
  row.appendChild(_badge(m.model_type || "other", "type"));
  row.appendChild(_badge(m.installed === true ? "Installed" : "Missing", m.installed === true ? "installed" : "missing"));
  row.appendChild(el("span", { class: "comfymodal-studio-model-size", text: _fmtSize(m.size) }));
  row.appendChild(el("span", {
    class: "comfymodal-studio-model-path",
    text: m.local_path || "",
    title: m.local_path || "",
  }));
  row.appendChild(el("span", {
    class: "comfymodal-studio-model-hash",
    text: m.hash ? String(m.hash).slice(0, 12) : "",
    title: m.hash || "",
  }));
  const src = m.source_urls && m.source_urls[0];
  row.appendChild(src
    ? el("a", { class: "comfymodal-studio-models-link", href: src, target: "_blank", rel: "noopener noreferrer", text: "source" })
    : el("span", { class: "comfymodal-studio-model-none" }));
  row.appendChild(el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "model-details",
    text: "Details",
    style: "font-size:10px;padding:4px 10px;",
    onclick: () => openModelDetailDialog(m, apiBase, view, refresh),
  }));
  return row;
}

// ── Model detail dialog ───────────────────────────────────────────────────

function openModelDetailDialog(model, apiBase, view, refresh) {
  const overlay = el("div", { class: "comfymodal-studio-dialog-overlay" });
  const backdrop = el("div", { class: "comfymodal-studio-dialog-backdrop", onclick: () => close() });
  const dialog = el("div", {
    class: "comfymodal-studio-dialog",
    "data-testid": "model-detail-dialog",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": "Model details",
  });

  dialog.appendChild(el("h3", { class: "comfymodal-studio-dialog-title", text: model.display_name || model.filename }));

  const statusEl = el("div", { class: "comfymodal-studio-dialog-status", style: "display:none;" });
  function showStatus(text, isError) {
    statusEl.style.display = "block";
    statusEl.textContent = text;
    statusEl.classList.toggle("error", !!isError);
  }

  // Read-only metadata
  const metaRows = [
    ["model_id", model.model_id],
    ["folder", model.folder],
    ["filename", model.filename],
    ["type", model.model_type],
    ["size", _fmtSize(model.size)],
    ["hash", model.hash],
    ["local path", model.local_path],
    ["installed", model.installed === true ? "yes" : "no"],
    ["provider", model.provider || ""],
    ["revision", model.revision || ""],
    ["discovered", model.discovered_at || ""],
    ["updated", model.updated_at || ""],
  ];
  dialog.appendChild(el("div", { class: "comfymodal-studio-dialog-section" }, [
    el("h4", { class: "comfymodal-studio-dialog-section-title", text: "Metadata" }),
    el("div", { class: "comfymodal-studio-model-detail-meta" },
      metaRows.map(([k, v]) => el("div", { class: "comfymodal-studio-model-detail-meta-row" }, [
        el("span", { class: "comfymodal-studio-model-detail-meta-key", text: k }),
        el("span", { class: "comfymodal-studio-model-detail-meta-val", text: v != null ? String(v) : "", title: v != null ? String(v) : "" }),
      ]))),
  ]));

  // Editable fields
  const values = {
    display_name: model.display_name || "",
    provider: model.provider || "",
    revision: model.revision || "",
    notes: model.notes || "",
    tags: (model.tags || []).join(", "),
    source_urls: (model.source_urls || []).join("\n"),
  };
  const inputs = {};
  inputs.display_name = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: values.display_name, oninput: (e) => { values.display_name = e.currentTarget.value; } });
  inputs.provider = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: values.provider, oninput: (e) => { values.provider = e.currentTarget.value; } });
  inputs.revision = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: values.revision, oninput: (e) => { values.revision = e.currentTarget.value; } });
  inputs.notes = el("textarea", { class: "comfymodal-studio-textarea", rows: 2, "data-testid": "model-notes-input", value: values.notes, oninput: (e) => { values.notes = e.currentTarget.value; } });
  inputs.tags = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: values.tags, placeholder: "comma, separated", oninput: (e) => { values.tags = e.currentTarget.value; } });
  inputs.source_urls = el("textarea", { class: "comfymodal-studio-textarea", rows: 3, value: values.source_urls, placeholder: "one URL per line", oninput: (e) => { values.source_urls = e.currentTarget.value; } });

  dialog.appendChild(el("div", { class: "comfymodal-studio-dialog-section" }, [
    el("h4", { class: "comfymodal-studio-dialog-section-title", text: "Edit" }),
    el("div", { class: "comfymodal-studio-editor-grid" }, [
      el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Display name" }), inputs.display_name]),
      el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Provider" }), inputs.provider]),
      el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Revision" }), inputs.revision]),
      el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Notes" }), inputs.notes]),
      el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Tags (comma separated)" }), inputs.tags]),
      el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Source URLs (one per line)" }), inputs.source_urls]),
    ]),
    statusEl,
    el("div", { class: "comfymodal-studio-dialog-actions" }, [
      el("button", {
        class: "comfymodal-primary-btn",
        "data-testid": "model-detail-save",
        text: "Save",
        style: "width:auto;",
        onclick: async () => {
          const resp = await updateModel(apiBase, model.model_id, {
            display_name: values.display_name.trim(),
            provider: values.provider.trim(),
            revision: values.revision.trim(),
            notes: values.notes,
            tags: values.tags.split(",").map((s) => s.trim()).filter(Boolean),
            source_urls: values.source_urls.split("\n").map((s) => s.trim()).filter(Boolean),
          });
          if (resp && resp.status === "ok") {
            const updated = resp.model || null;
            if (updated) {
              const md = view.modelsData;
              const idx = md.models.findIndex((m) => m.model_id === model.model_id);
              if (idx !== -1) md.models[idx] = Object.assign({}, md.models[idx], updated);
            }
            close();
            refresh();
          } else {
            showStatus("Could not save: " + ((resp && resp.message) || "request failed"), true);
          }
        },
      }),
      el("button", { class: "comfymodal-secondary-btn", text: "Cancel", onclick: close }),
    ]),
  ]));

  // Download approval request — only for missing models with a known source.
  if (model.installed !== true && model.source_urls && model.source_urls[0]) {
    dialog.appendChild(renderDownloadRequestSection(model, apiBase, showStatus));
  }

  function close() {
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }

  overlay.appendChild(backdrop);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
}

function renderDownloadRequestSection(model, apiBase, showStatus) {
  const wrap = el("div", { class: "comfymodal-studio-dialog-section", "data-testid": "model-download-section" });
  wrap.appendChild(el("h4", { class: "comfymodal-studio-dialog-section-title", text: "Request download" }));

  const panel = el("div", { class: "comfymodal-studio-download-panel" });
  const urlIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: model.source_urls[0] });
  const folderSel = el("select", { class: "comfymodal-studio-model-picker" });
  const buckets = MODEL_BUCKETS[model.model_type] || MODEL_BUCKETS.other;
  // Offer the full sensible set, defaulting to the canonical bucket for the type.
  const allBuckets = Array.from(new Set(Object.values(MODEL_BUCKETS)));
  allBuckets.forEach((b) => folderSel.appendChild(el("option", { value: b, text: b })));
  folderSel.value = buckets;
  const filenameIn = el("input", { type: "text", class: "comfymodal-studio-wf-input", value: model.filename || "" });

  const formStatus = el("div", { class: "comfymodal-studio-dialog-status", style: "display:none;" });
  const infoEl = el("div", { class: "comfymodal-studio-dialog-note", style: "display:none;" });

  const submitBtn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "model-download-request",
    text: "Request download",
    onclick: async () => {
      submitBtn.disabled = true;
      const resp = await requestModelInstall(apiBase, {
        folder: folderSel.value,
        filename: (filenameIn.value || "").trim(),
        url: (urlIn.value || "").trim(),
      });
      submitBtn.disabled = false;
      if (resp && resp.status === "ok") {
        formStatus.style.display = "none";
        const req = resp.request || {};
        infoEl.style.display = "block";
        infoEl.textContent =
          "Approval request recorded \u2014 nothing was downloaded. "
          + "Source kind: " + (req.source_kind || "url")
          + (req.approved ? " \u00b7 approved" : "")
          + (resp.note ? " \u00b7 " + resp.note : "");
      } else {
        formStatus.style.display = "block";
        formStatus.textContent = "Request failed: " + ((resp && resp.message) || "request failed");
        formStatus.classList.add("error");
      }
    },
  });

  panel.appendChild(el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "URL" }), urlIn]));
  panel.appendChild(el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Folder" }), folderSel]));
  panel.appendChild(el("div", { class: "comfymodal-studio-backend-field" }, [el("label", { text: "Filename" }), filenameIn]));
  panel.appendChild(formStatus);
  panel.appendChild(el("p", { class: "comfymodal-studio-dialog-note", text: "This only requests approval to download \u2014 the file is never fetched from here." }));
  panel.appendChild(el("div", { class: "comfymodal-studio-dialog-actions", style: "justify-content:flex-start;" }, [submitBtn]));
  panel.appendChild(infoEl);

  wrap.appendChild(panel);
  return wrap;
}

// ── Dependency section ────────────────────────────────────────────────────

/**
 * Render the version dependency section.
 * @param {object} version - selected workflow version (may carry
 *   dependency_metadata used as a fallback when the endpoint is unavailable)
 * @param {object|null} deps - GET .../dependencies payload or null (loading /
 *   failed / endpoint missing)
 * @param {function} [refreshHandler] - optional click handler for the Refresh
 *   button (data-testid="dependencies-refresh")
 * @param {object} [opts] - optional parity context:
 *   { apiBase } enables the explicit per-node install-request action on
 *   missing custom-node rows; { onFindInLibrary(filename) } enables the
 *   contextual "Find in library" handoff on missing model rows.  Both are
 *   user-click-only; nothing here installs or downloads automatically.
 * @returns {HTMLElement}
 */
export function renderDependencySection(version, deps, refreshHandler, opts) {
  const ctx = opts || {};
  const section = el("div", {
    class: "comfymodal-studio-section",
    "data-testid": "dependencies-summary",
  });
  section.appendChild(el("div", { class: "comfymodal-studio-section-head" }, [
    el("h3", { class: "comfymodal-studio-section-title", text: "Dependencies" }),
    typeof refreshHandler === "function"
      ? el("button", {
          class: "comfymodal-secondary-btn",
          "data-testid": "dependencies-refresh",
          text: "Refresh",
          style: "font-size:10px;padding:4px 10px;",
          onclick: refreshHandler,
        })
      : null,
  ]));

  const hasLive = !!(deps && deps.status === "ok");

  if (hasLive) {
    const summary = deps.summary || {};
    const ready = summary.ready === true;
    const attention = summary.attention || 0;
    section.appendChild(el("div", {
      class: "comfymodal-studio-dependency-banner " + (ready ? "ready" : "attention"),
      "data-testid": "dependency-status",
    }, [
      el("span", {
        class: "comfymodal-studio-dependency-banner-label",
        text: ready
          ? "Ready"
          : "Incomplete \u2014 " + attention + " dependenc" + (attention === 1 ? "y" : "ies")
            + (attention === 1 ? " needs" : " need") + " attention",
      }),
    ]));

    const models = Array.isArray(deps.models) ? deps.models : [];
    const nodes = Array.isArray(deps.custom_nodes) ? deps.custom_nodes : [];

    if (models.length) {
      section.appendChild(el("div", { class: "comfymodal-studio-dependency-group", "data-testid": "dependency-models" }, [
        el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Models" }),
        el("div", { class: "comfymodal-studio-dependency-table" }, models.map((m) => renderDependencyModelRow(m, ctx))),
      ]));
    }
    if (nodes.length) {
      section.appendChild(el("div", { class: "comfymodal-studio-dependency-group", "data-testid": "dependency-nodes" }, [
        el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Custom nodes" }),
        el("div", { class: "comfymodal-studio-dependency-table" }, nodes.map((n) => renderDependencyNodeRow(n, ctx))),
      ]));
    }
    // Graph artifacts (frontend-only UUIDs / display titles recorded as
    // types) can never resolve to an installed pack, so the backend reports
    // them separately instead of "missing". Surface the skip truthfully.
    const skipped = (deps && Array.isArray(deps.unresolvable)) ? deps.unresolvable : [];
    if (skipped.length) {
      section.appendChild(el("p", {
        class: "comfymodal-studio-dependencies-note",
        "data-testid": "dependency-artifacts-note",
        text: `${skipped.length} graph artifact${skipped.length === 1 ? "" : "s"} skipped — not installable node classes.`,
        title: skipped.map((u) => (u && u.name) || "").filter(Boolean).join(", "),
      }));
    }

    const metaChips = renderMetadataChips(version);
    if (!models.length && !nodes.length && !metaChips) {
      section.appendChild(el("p", { class: "comfymodal-studio-dependencies-note", text: "No dependencies recorded for this version." }));
    }
  } else {
    section.appendChild(el("p", { class: "comfymodal-studio-dependencies-note", text: "Dependency information is unavailable for this version." }));
  }

  // Recorded metadata from the captured graph (model stack / node classes).
  // Always rendered so older clients and tests that only have
  // dependency_metadata still surface the recorded stack.
  const metaChips = renderMetadataChips(version);
  if (metaChips) section.appendChild(metaChips);

  return section;
}

function renderMetadataChips(version) {
  const dep = (version && version.dependency_metadata) || {};
  const stack = _flattenStack(dep.model_stack);
  const classes = Array.isArray(dep.node_classes) ? dep.node_classes.map(String) : [];
  if (stack.length === 0 && classes.length === 0) return null;
  const wrap = el("div", { class: "comfymodal-studio-dependencies-summary" });
  if (stack.length) {
    wrap.appendChild(el("div", { class: "comfymodal-studio-dependencies-group" }, [
      el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Model stack" }),
      el("div", { class: "comfymodal-studio-dependencies-chips" },
        stack.map((m) => el("span", { class: "comfymodal-studio-wf-chip cm-chip", "data-tone": "neutral", text: m }))),
    ]));
  }
  if (classes.length) {
    wrap.appendChild(el("div", { class: "comfymodal-studio-dependencies-group" }, [
      el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Node classes" }),
      el("div", { class: "comfymodal-studio-dependencies-chips" },
        classes.map((c) => el("span", { class: "comfymodal-studio-wf-chip cm-chip", "data-tone": "neutral", text: c }))),
    ]));
  }
  return wrap;
}

function renderDependencyModelRow(m, ctx) {
  const row = el("div", {
    class: "comfymodal-studio-dependency-row",
    "data-testid": "dependency-model-row",
    "data-model-key": m.key || "",
  });
  row.appendChild(_badge(m.role || "model", "role"));
  row.appendChild(el("span", { class: "comfymodal-studio-dependency-name", text: m.filename || "", title: m.filename || "" }));
  row.appendChild(_stateBadgeFor(m.state));
  if (m.state === "installed") {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-detail", text: m.local_path || m.folder || "" }));
  } else {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-detail", text: "Not installed" }));
    const src = m.source_urls && m.source_urls[0];
    if (src) {
      row.appendChild(el("a", { class: "comfymodal-studio-models-link", href: src, target: "_blank", rel: "noopener noreferrer", text: "source" }));
    }
    // Manager catalog fallback: per-filename download + page URLs when the
    // library record carries none.
    const managed = ctx && ctx.managerModelsByFilename && m.filename
      ? ctx.managerModelsByFilename[m.filename] : null;
    const managerUrl = managed && managed.url ? managed.url : "";
    const managerRef = managed && managed.reference ? managed.reference : "";
    if (managerRef && managerRef !== src) {
      row.appendChild(el("a", { class: "comfymodal-studio-models-link", href: managerRef, target: "_blank", rel: "noopener noreferrer", text: "manager source", title: (managed && managed.name) || m.filename }));
    }
    const downloadUrl = src || managerUrl;
    if (downloadUrl && ctx && typeof ctx.onDownloadModel === "function") {
      row.appendChild(renderModelDownloadControl(m, downloadUrl, ctx));
    }
    // Contextual handoff into the Model Library filter — no second
    // model-management implementation, just a prefilled library query.
    if (ctx && typeof ctx.onFindInLibrary === "function" && m.filename) {
      row.appendChild(el("button", {
        class: "comfymodal-secondary-btn",
        "data-testid": "dependency-model-find",
        text: "Find in library",
        style: "font-size:10px;padding:2px 8px;width:auto;",
        onclick: () => ctx.onFindInLibrary(m.filename),
      }));
    }
  }
  return row;
}

function renderModelDownloadControl(m, downloadUrl, ctx) {
  const wrap = el("span", { class: "comfymodal-studio-dependency-request" });
  const btn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "dependency-model-download",
    "data-model-key": m.key || "",
    text: "Download on Modal",
    style: "font-size:10px;padding:2px 8px;width:auto;",
    onclick: async () => {
      if (btn.disabled) return;
      btn.disabled = true;
      btn.textContent = "Downloading…";
      note.style.display = "block";
      note.textContent = "Download requested…";
      note.classList.remove("error");
      try {
        const res = await ctx.onDownloadModel({
          filename: m.filename || "",
          url: downloadUrl,
          savePath: m.folder || "",
        });
        if (res && res.ok) {
          note.textContent = res.message || "Downloaded.";
          note.classList.remove("error");
          if (typeof ctx.onDepsRefresh === "function") {
            try { await ctx.onDepsRefresh(); } catch (e) { /* refresh is best-effort */ }
          }
        } else {
          note.textContent = (res && res.message) || "Download failed.";
          note.classList.add("error");
          btn.disabled = false;
          btn.textContent = "Download on Modal";
        }
      } catch (err) {
        note.style.display = "block";
        note.textContent = "Download failed: " + ((err && err.message) || "request failed");
        note.classList.add("error");
        btn.disabled = false;
        btn.textContent = "Download on Modal";
      }
    },
  });
  const note = el("div", {
    class: "comfymodal-studio-dependency-request-note",
    style: "display:none;font-size:10px;color:#888;margin-top:2px;",
  });
  wrap.appendChild(btn);
  wrap.appendChild(note);
  return wrap;
}

function renderDependencyNodeRow(n, ctx) {
  const row = el("div", {
    class: "comfymodal-studio-dependency-row",
    "data-testid": "dependency-node-row",
    "data-node-name": n.name || "",
  });
  row.appendChild(el("span", { class: "comfymodal-studio-dependency-name", text: n.name || "", title: n.name || "" }));
  row.appendChild(_stateBadgeFor(n.state));
  row.appendChild(el("span", {
    class: "comfymodal-studio-dependency-detail",
    text: n.installed_commit ? _shortCommit(n.installed_commit) : "",
    title: n.installed_commit || "",
  }));
  if (n.required_revision) {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-detail", text: "required " + n.required_revision }));
  }
  // I6 contextual handoff (H7 model-row parity): a MISSING custom-node row
  // offers "Find in registry", which opens the single Model Library view
  // scoped to its registry section, filtered to this identifier.  Navigation
  // only — no install request fires from this control.
  if (n.state === "missing" && n.name && ctx && typeof ctx.onFindInRegistry === "function") {
    row.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      type: "button",
      "data-testid": "dependency-node-find-registry",
      text: "Find in registry",
      style: "font-size:10px;padding:2px 8px;width:auto;",
      onclick: () => ctx.onFindInRegistry(n.name),
    }));
  }
  if (n.install_path) {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-path", text: n.install_path, title: n.install_path }));
  }
  if (n.repository_url) {
    row.appendChild(el("a", { class: "comfymodal-studio-models-link", href: n.repository_url, target: "_blank", rel: "noopener noreferrer", text: "repo" }));
  }
  // Missing node with a known repo: when ComfyUI-Manager is detected the
  // caller may provide an explicit install action; otherwise the existing
  // record-only approval request flow is preserved.  Nothing installs on
  // render — both controls require an explicit click.
  if (n.state === "missing" && n.repository_url) {
    const installedNames = Array.isArray(ctx && ctx.managerInstalledNames) ? ctx.managerInstalledNames : [];
    const isKnownInstalled = installedNames.some(
      (name) => name && (name === n.name || name === n.repository_url)
    );
    if (isKnownInstalled) {
      row.appendChild(el("span", {
        class: "comfymodal-studio-dependency-detail",
        "data-testid": "dependency-node-manager-installed",
        text: "Installed (restart may be required)",
      }));
    } else if (ctx && ctx.managerAvailable === true && typeof ctx.onInstallPack === "function") {
      row.appendChild(el("button", {
        class: "comfymodal-secondary-btn",
        type: "button",
        "data-testid": "dependency-node-manager-install",
        "data-node-name": n.name || "",
        text: (ctx.installingPack && ctx.installingPack === n.name) ? "Installing\u2026" : "Install via Manager",
        style: "font-size:10px;padding:2px 8px;width:auto;",
        onclick: () => ctx.onInstallPack(n),
      }));
    } else if (ctx && ctx.apiBase) {
      row.appendChild(renderNodeInstallRequestControl(n, ctx.apiBase));
    }
  }
  // Missing packs without a known repository still get the record-only
  // approval request: every missing row offers an action, URL or not.
  if (n.state === "missing" && !n.repository_url && ctx && ctx.apiBase) {
    row.appendChild(renderNodeInstallRequestControl(n, ctx.apiBase));
  }
  return row;
}

function renderNodeInstallRequestControl(node, apiBase) {
  const wrap = el("span", { class: "comfymodal-studio-dependency-request" });
  const btn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "dependency-node-install-request",
    text: "Request install",
    style: "font-size:10px;padding:2px 8px;width:auto;",
    onclick: async () => {
      if (btn.disabled) return; // request dedupe while in flight
      btn.disabled = true;
      btn.textContent = "Requesting\u2026";
      try {
        const resp = await requestCustomNodeInstall(apiBase, {
          name: node.name || "",
          repo_url: node.repository_url || "",
          revision: node.required_revision || "",
        });
        note.style.display = "block";
        if (resp && resp.status === "ok") {
          note.textContent = "Approval recorded \u2014 nothing was installed."
            + (resp.note ? " " + resp.note : "");
          note.classList.remove("error");
        } else {
          note.textContent = "Request failed: " + ((resp && resp.message) || "request failed");
          note.classList.add("error");
          btn.disabled = false;
          btn.textContent = "Request install";
        }
      } catch (err) {
        note.style.display = "block";
        note.textContent = "Request failed: " + (err && err.message ? err.message : "request failed");
        note.classList.add("error");
        btn.disabled = false;
        btn.textContent = "Request install";
      }
    },
  });
  const note = el("div", {
    class: "comfymodal-studio-dialog-note",
    "data-testid": "dependency-node-install-note",
    style: "display:none;",
  });
  wrap.appendChild(btn);
  wrap.appendChild(note);
  return wrap;
}

// ── Model picker (preset editor "Model choices") ──────────────────────────

/**
 * Build a <select> of library models for a model-kind preset role.
 * @param {object} opts
 * @param {string[]} opts.compatibleModels - frozen list of compatible model
 *   filenames (when non-empty, only matching library models are offered)
 * @param {string} opts.currentValue - saved value for this role
 * @param {object[]} opts.models - library model records (may be [] while
 *   loading — the picker then shows a "Loading models…" placeholder)
 * @param {function} opts.onSelect - fired with the chosen filename
 * @returns {HTMLElement}
 */
export function renderModelPicker({ compatibleModels, currentValue, models, onSelect }) {
  const sel = el("select", { class: "comfymodal-studio-model-picker", "data-testid": "model-choice-select" });
  const available = Array.isArray(models) ? models : [];
  const current = currentValue != null ? String(currentValue) : "";

  let pool = available;
  if (Array.isArray(compatibleModels) && compatibleModels.length > 0) {
    const set = new Set(compatibleModels.map(String));
    pool = available.filter((m) => set.has(String(m.filename)));
  }

  const addOption = (value, label) => {
    sel.appendChild(el("option", { value: value, text: label }));
  };

  if (available.length === 0) {
    addOption("", "Loading models\u2026");
  } else {
    if (!current) addOption("", "Select a model\u2026");
    pool.forEach((m) => {
      addOption(
        String(m.filename),
        (m.display_name || m.filename) + " (" + m.filename + ")" + (m.installed ? "" : " [missing]")
      );
    });
    if (current && !pool.some((m) => String(m.filename) === current)) {
      addOption(current, current + " (saved)");
    }
    if (current) sel.value = current;
  }

  sel.addEventListener("change", () => {
    if (typeof onSelect === "function") onSelect(sel.value);
  });
  return sel;
}
