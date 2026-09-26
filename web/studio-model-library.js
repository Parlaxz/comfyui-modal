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
// Scans/refreshes run ONLY on explicit user action (never on render). The
// dependency rows expose explicit-click install actions (Queue install /
// Install now for sourced models, an explicit URL install for source-less
// models — the backend downloads into the Modal workspace/volume, never the
// browser — and a Manager-backed Install now for custom nodes); nothing
// installs on render. The model detail dialog keeps its record-only request
// flow.

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
  batchInstallModels,
  installSingleModel,
  modelDownloadStatus,
  managerInstallNode,
  managerQueueInstall,
  managerQueueStart,
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
        : (kind === "downloading" || kind === "queued") ? "running"
          : "neutral";
  return el("span", {
    class: "comfymodal-studio-model-badge " + kind + " cm-chip",
    "data-tone": tone,
    text: text,
  });
}

// Text/kind per dependency state. The dependency row's state badge is the
// single source of truth for install state, so the in-flight transition
// ("Downloading\u2026") can update the SAME node in place without re-rendering.
const _STATE_BADGE = {
  installed: ["Installed", "installed"],
  missing: ["Missing", "missing"],
  wrong_version: ["Wrong version", "warning"],
  downloading: ["Downloading", "downloading"],
  queued: ["Queued", "queued"],
};

/** Set a badge node's text/kind/tone in place (keeps cm-chip tone truthful). */
function _applyBadge(node, text, kind) {
  const tone =
    kind === "installed" ? "ok"
      : (kind === "missing" || kind === "warning") ? "warn"
        : (kind === "downloading" || kind === "queued") ? "running"
          : "neutral";
  node.className = "comfymodal-studio-model-badge " + kind + " cm-chip";
  node.setAttribute("data-tone", tone);
  node.textContent = text;
}

/** Reset a badge node to a dependency state (text + kind + data-state). */
function _applyStateBadge(node, state) {
  const entry = _STATE_BADGE[state] || ["Unknown", "unknown"];
  _applyBadge(node, entry[0], entry[1]);
  node.setAttribute("data-state", state || "unknown");
  return node;
}

function _stateBadgeFor(state) {
  return _applyStateBadge(el("span", {}), state);
}

/**
 * Apply an in-flight badge (queued/downloading) to an EXISTING state badge
 * node. Public so the wizard can re-apply its tracked status after a re-render
 * on the row's real state badge — never a detached supplemental chip. `text`
 * overrides the default label (a model's queue action reads
 * "Queued for download" while a custom-node queue reads "Queued").
 */
export function applyDependencyInflightBadge(node, kind, text) {
  if (!node) return node;
  const entry = _STATE_BADGE[kind] || ["Unknown", "unknown"];
  _applyBadge(node, text || entry[0], entry[1]);
  node.setAttribute("data-state", kind || "unknown");
  return node;
}

/** Apply a report state (installed/missing/wrong_version) to a badge node. */
export function applyDependencyStateBadge(node, state) {
  return _applyStateBadge(node, state);
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

// ── Manager catalog lookups (custom nodes + models) ───────────────────────
//
// Manager data is advisory only: it can supply a pack repository or a model
// source URL when the persisted library record has none. Nothing here
// installs anything; every install stays an explicit user click on a row.

/** Basename for path-like names ("a/b/c.safetensors" → "c.safetensors"). */
function _basename(name) {
  const value = String(name || "");
  const idx = Math.max(value.lastIndexOf("/"), value.lastIndexOf("\\"));
  return idx === -1 ? value : value.slice(idx + 1);
}

// Manager's type → ComfyUI folder behavior (mirrors Manager's
// model_dir_name_map). Used to normalize a "default" save_path and to match a
// dependency role against a catalog record's type without cross-type mixups.
const _MANAGER_TYPE_FOLDERS = {
  checkpoint: "checkpoints",
  checkpoints: "checkpoints",
  unclip: "checkpoints",
  lora: "loras",
  loras: "loras",
  lycoris: "loras",
  vae: "vae",
  clip: "text_encoders",
  text_encoder: "text_encoders",
  text_encoders: "text_encoders",
  unet: "diffusion_models",
  diffusion_model: "diffusion_models",
  diffusion_models: "diffusion_models",
  t2i_adapter: "controlnet",
  "t2i-adapter": "controlnet",
  "t2i-style": "controlnet",
  controlnet: "controlnet",
  clip_vision: "clip_vision",
  gligen: "gligen",
  upscale: "upscale_models",
  upscaler: "upscale_models",
  upscale_models: "upscale_models",
  embedding: "embeddings",
  embeddings: "embeddings",
  vae_approx: "vae_approx",
  hypernetworks: "hypernetworks",
  style_models: "style_models",
  model_patches: "model_patches",
};

/** Map a Manager model type to a ComfyUI folder, or "" when unknown. */
export function managerModelFolder(type) {
  const key = String(type == null ? "" : type).trim().toLowerCase();
  return (key && _MANAGER_TYPE_FOLDERS[key]) || "";
}

/**
 * Normalize a Manager model save_path. Manager uses "default" to mean "let
 * ComfyUI pick the folder for this model type"; resolve it through the
 * type→folder map so a Modal install lands in a real folder. An explicit,
 * non-default path is preserved as-is.
 */
export function normalizeManagerSavePath(savePath, type) {
  const raw = String(savePath == null ? "" : savePath).trim();
  if (raw && raw.toLowerCase() !== "default") return raw;
  const folder = managerModelFolder(type);
  // Never emit the literal "default": an unknown type falls back to "" so the
  // caller can use its own role→folder bucket.
  return folder || "";
}

function _folderFromSavePath(savePath) {
  const raw = String(savePath == null ? "" : savePath).trim();
  if (!raw || raw.toLowerCase() === "default") return "";
  const head = raw.split("/")[0];
  return _MANAGER_TYPE_FOLDERS[String(head).toLowerCase()] || head;
}

function _roleMatchesType(role, record) {
  if (!role || !record || typeof record !== "object") return true;
  const roleFolder = managerModelFolder(role) || String(role).toLowerCase();
  const recordFolder = managerModelFolder(record.type) || _folderFromSavePath(record.savePath);
  if (!roleFolder || !recordFolder) return true;
  return roleFolder === recordFolder;
}

/**
 * Resolve a missing dependency's Manager model record by filename. Exact
 * filename wins; a path-like dependency filename otherwise matches the
 * catalog basename (Manager catalogs basenames). A match is rejected when the
 * dependency role and the catalog type map to different folders, so
 * same-basename files of another type are never installed in the wrong place.
 */
export function matchManagerModel(m, map) {
  if (!map || !m || !m.filename) return null;
  const keys = [String(m.filename)];
  const base = _basename(m.filename);
  if (base && base !== m.filename) keys.push(base);
  for (const key of keys) {
    const record = map[key];
    if (record && _roleMatchesType(m.role, record)) return record;
  }
  return null;
}

/**
 * Pure: build the filename → Manager model record map consumed by
 * `matchManagerModel` / the dependency rows. Records are keyed by exact
 * filename and by basename (Manager catalogs basenames); a `default`
 * save_path is normalized through the type→folder map so an install lands in
 * a real folder. Advisory only — nothing here downloads or installs.
 */
export function buildManagerModelIndex(models) {
  const map = {};
  (Array.isArray(models) ? models : []).forEach((m) => {
    if (!m || !m.filename) return;
    const record = {
      url: m.url || "",
      reference: m.reference || "",
      savePath: normalizeManagerSavePath(m.save_path, m.type),
      type: m.type || "",
      name: m.name || "",
      installed: m.installed,
    };
    const filename = String(m.filename);
    if (!map[filename]) map[filename] = record;
    const base = _basename(filename);
    if (base && base !== filename && !map[base]) map[base] = record;
  });
  return map;
}

function _managerModelFor(m, ctx) {
  return matchManagerModel(m, ctx && ctx.managerModelsByFilename);
}

/**
 * Prefer `repository`, then `files[0]`. `reference` is intentionally NOT used:
 * for CNR packs it is a registry page, not an installable git URL.
 */
function _managerPackRepo(info) {
  if (!info || typeof info !== "object") return "";
  if (typeof info.repository === "string" && info.repository) return info.repository;
  const files = Array.isArray(info.files) ? info.files : [];
  if (typeof files[0] === "string" && files[0]) return files[0];
  return "";
}

function _managerNodePacks(packList) {
  if (Array.isArray(packList)) {
    const out = {};
    packList.forEach((p) => {
      if (p && (p.id || p.title || p.name)) out[p.id || p.title || p.name] = p;
    });
    return out;
  }
  if (packList && typeof packList === "object") {
    if (packList.node_packs && typeof packList.node_packs === "object") return packList.node_packs;
    if (packList.packs && typeof packList.packs === "object") return packList.packs;
  }
  return {};
}

/** "owner/repo" for a GitHub URL, else "" (used to join aux ids). */
function _repoSlug(url) {
  const value = String(url || "").trim().replace(/\.git$/i, "");
  const match = value.match(/github\.com[/:]([^/]+)\/([^/?#]+)/i);
  return match ? (match[1] + "/" + match[2]).toLowerCase() : "";
}

function _safeRegExp(source) {
  try {
    const re = new RegExp(String(source));
    return re.global ? new RegExp(String(source).replace(/[gmy]+$/, "")) : re;
  } catch (e) {
    return null;
  }
}

function _indexByKey(index, candidate, record) {
  const key = String(candidate == null ? "" : candidate).trim().toLowerCase();
  if (key && record && !index[key]) index[key] = record;
}

/**
 * Pure: build a pack lookup from Manager's pack list
 * (`/customnode/getlist`) and class mappings (`/customnode/getmappings`).
 *
 * Returns `{ packs, byClass, preemptions, patterns }`. Keys are matched
 * case-insensitively and packs are indexed by their key, CNR id, aux id,
 * repository/files URL, repository slug and reference — never by an invented
 * URL. Resolution order is documented on `_resolveManagerPack`. Packs
 * WITHOUT a repository are still indexed (pure-CNR packs install by record
 * through Manager's queue, not by URL).
 */
export function buildManagerPackIndex(packList, mappings) {
  const packs = {};
  const byClass = {};
  const preemptions = {};
  const patterns = [];
  const rawPacks = _managerNodePacks(packList);

  const registerPack = (key, rawInfo) => {
    const info = rawInfo && typeof rawInfo === "object" ? rawInfo : {};
    const repositoryUrl = _managerPackRepo(info);
    const record = {
      key: String(key || ""),
      cnrId: String(info.id || key || ""),
      auxId: String(info.aux_id || info.auxId || ""),
      name: String(info.title || info.name || key || ""),
      repository: String(info.repository || ""),
      repository_url: repositoryUrl,
      reference: String(info.reference || ""),
      files: Array.isArray(info.files) ? info.files.slice() : [],
      version: info.version == null ? "" : String(info.version),
      selected_version: info.selected_version == null ? "" : String(info.selected_version),
      channel: info.channel == null ? "" : String(info.channel),
      mode: info.mode == null ? "" : String(info.mode),
      install_type: info.install_type == null ? "" : String(info.install_type),
      nodename_pattern: info.nodename_pattern == null ? "" : String(info.nodename_pattern),
    };
    const repoUrl = record.repository || record.files[0] || "";
    [
      key,
      record.cnrId,
      record.auxId,
      record.repository,
      record.reference,
      record.files[0],
      repoUrl && _basename(repoUrl),
      _repoSlug(repoUrl || record.reference),
    ].forEach((candidate) => _indexByKey(packs, candidate, record));
    if (record.nodename_pattern) {
      const re = _safeRegExp(record.nodename_pattern);
      if (re) patterns.push({ re: re, record: record });
    }
    if (Array.isArray(info.preemptions)) {
      info.preemptions.forEach((cls) => _indexByKey(preemptions, cls, record));
    }
    return record;
  };

  Object.keys(rawPacks).forEach((key) => registerPack(key, rawPacks[key]));

  if (mappings && typeof mappings === "object") {
    Object.keys(mappings).forEach((key) => {
      const entry = mappings[key];
      const classes = Array.isArray(entry) ? entry[0] : (entry && entry.classes);
      const meta = Array.isArray(entry) ? (entry[1] || {}) : {};
      const record = packs[String(key).toLowerCase()] || packs[_repoSlug(key)];
      if (record) {
        if (Array.isArray(meta.preemptions)) {
          meta.preemptions.forEach((cls) => _indexByKey(preemptions, cls, record));
        }
        if (meta.nodename_pattern) {
          const re = _safeRegExp(meta.nodename_pattern);
          if (re) patterns.push({ re: re, record: record });
        }
      }
      (Array.isArray(classes) ? classes : []).forEach((cls) => {
        if (record) _indexByKey(byClass, cls, record);
      });
    });
  }
  return { packs, byClass, preemptions, patterns };
}

/**
 * Resolve a missing node's pack from the Manager index. Order matches
 * Manager: explicit CNR/aux identity first, then preemptions, then the exact
 * class mapping, then `nodename_pattern` regexes. Never guesses a URL — only
 * case-insensitive matches already present in the index qualify.
 */
function _resolveManagerPack(n, ctx) {
  const index = ctx && ctx.managerPacks;
  if (!index || !n) return null;
  const packs = index.packs || {};
  const identities = [n.cnr_id, n.aux_id];
  for (const raw of identities) {
    if (!raw) continue;
    const value = String(raw);
    const record =
      packs[value.toLowerCase()] ||
      packs[_repoSlug(value)] ||
      packs[_basename(value).toLowerCase()];
    if (record) return record;
  }
  const classes = Array.isArray(n.classes) ? n.classes : (n.classes ? [n.classes] : []);
  const lowered = classes.map((c) => String(c == null ? "" : c).toLowerCase()).filter(Boolean);
  for (const lc of lowered) {
    const record = index.preemptions && index.preemptions[lc];
    if (record) return record;
  }
  for (const lc of lowered) {
    const record = index.byClass && index.byClass[lc];
    if (record) return record;
  }
  for (const cls of classes) {
    const value = String(cls == null ? "" : cls);
    if (!value) continue;
    for (const pattern of index.patterns || []) {
      if (pattern.re.test(value)) return pattern.record;
    }
  }
  return null;
}

/**
 * Decide how a missing node/pack should be installed. Explicit, single
 * target: ANY pack identified by a Manager record installs through Manager's
 * CNR queue — including records whose version metadata is blank/unknown —
 * because the queue payload supplies safe defaults. Only a truly unmatched
 * pack (no Manager record) falls back to the dependency report's explicit
 * repository URL via the security-gated git_url route; otherwise no target.
 */
export function resolveNodeInstall(node, managerPacks) {
  const n = node || {};
  const pack = _resolveManagerPack(n, { managerPacks: managerPacks });
  // Identified Manager packs never touch the git_url 403 gate; the CNR queue
  // installs by record (id + safe defaults), not by repository URL.
  if (pack) {
    return { kind: "cnr", pack: pack, url: "", name: pack.name || n.name || "" };
  }
  // Truly unmatched: only an explicit repository from the dependency report
  // qualifies for the (still security-gated) git_url fallback.
  const repo = n.repository_url || "";
  if (repo) {
    return { kind: "git", pack: null, url: repo, name: n.name || "" };
  }
  return { kind: "none", pack: null, url: "", name: n.name || "" };
}

function _queueInstallPayload(pack) {
  const files = Array.isArray(pack.files) ? pack.files.slice() : [];
  return {
    id: pack.cnrId || pack.repository || files[0] || "",
    version: pack.version || "unknown",
    selected_version: pack.selected_version || "latest",
    channel: pack.channel || "default",
    mode: pack.mode || "default",
    repository: pack.repository || files[0] || "",
    files: files,
    ui_id: String(pack.key || pack.cnrId || ""),
    install_type: pack.install_type || "",
    skip_post_install: false,
  };
}

/**
 * Perform an explicit Manager install for a resolved plan. CNR records go
 * through POST /manager/queue/install + /manager/queue/start (no git_url 403
 * gate); an unmatched pack with an explicit repository keeps the dedicated
 * git_url fallback. A plan with no target returns a truthful message and
 * never guesses a URL. Never reboots.
 */
export async function performManagerInstall(plan) {
  if (!plan || plan.kind === "none") {
    return { ok: false, message: "No Manager install target identified for this pack." };
  }
  try {
    if (plan.kind === "cnr") {
      const queued = await managerQueueInstall(_queueInstallPayload(plan.pack));
      if (!queued) return { ok: false, message: "Could not reach ComfyUI-Manager." };
      if (queued.status === 403) {
        return { ok: false, message: "Manager refused the CNR install (403). Raise Manager's security level, then retry." };
      }
      if (!queued.ok) {
        const msg = (queued.data && (queued.data.message || queued.data.error)) || ("HTTP " + queued.status);
        return { ok: false, message: "Install failed: " + msg };
      }
      const started = await managerQueueStart();
      if (!started || !started.ok) {
        return { ok: false, message: "Install queued, but Manager did not start it. Open ComfyUI-Manager and press Start." };
      }
      return { ok: true, message: "Install queued through ComfyUI-Manager \u2014 restart ComfyUI to load it." };
    }
    // Unknown/nightly git pack: still security-gated, never bypassed.
    const resp = await managerInstallNode(plan.url);
    if (!resp) return { ok: false, message: "Could not reach ComfyUI-Manager." };
    if (resp.status === 403) {
      return { ok: false, message: "Manager refused the install (403). Set allow_git_url_install=true, use a loopback session, then restart ComfyUI." };
    }
    if (resp.ok) return { ok: true, message: "Installed \u2014 restart ComfyUI to load it." };
    const msg = (resp.data && (resp.data.message || resp.data.error)) || ("HTTP " + resp.status);
    return { ok: false, message: "Install failed: " + msg };
  } catch (err) {
    return { ok: false, message: "Install failed: " + ((err && err.message) || "request failed") };
  }
}

// ── Remote Modal model-volume availability overlay ──────────────────────
//
// The remote model volume (GET /comfymodal/models -> list_models_cpu) is the
// availability authority. Local zero-byte files are intentional placeholders:
// a dependency row is "remote available" only when its remote entry's size is
// greater than zero, regardless of the local placeholder's size. Availability
// is derived only from basename + role/folder alias; wrong_version stays a
// compatibility signal. Nothing here downloads or installs — the overlay is a
// display projection of the report.

// Mirror of the backend's WORKFLOW_ROLE_FOLDERS aliases (dependency_resolver).
const _REMOTE_ROLE_FOLDER_ALIASES = {
  checkpoint: ["checkpoints"],
  unet: ["unet", "diffusion_models"],
  clip: ["clip", "text_encoders"],
  vae: ["vae"],
  lora: ["loras"],
  controlnet: ["controlnet"],
};

/** Lowercased basename of a path-like model reference. */
function _remoteNameKey(name) {
  const value = String(name || "").replace(/\\/g, "/");
  const base = value.slice(value.lastIndexOf("/") + 1);
  return base.toLowerCase();
}

/** Folders that satisfy a dependency role, aliases included. */
function _remoteFolderAliases(role) {
  return _REMOTE_ROLE_FOLDER_ALIASES[String(role || "").trim().toLowerCase()] || [];
}

/**
 * Index a normalized /comfymodal/models inventory by lowercased basename.
 * @param {Array} inventory - entries from listRemoteModels()
 * @returns {Map<string, Array<object>>}
 */
export function buildRemoteModelIndex(inventory) {
  const index = new Map();
  (Array.isArray(inventory) ? inventory : []).forEach((entry) => {
    if (!entry || typeof entry !== "object") return;
    const key = _remoteNameKey(entry.name);
    if (!key) return;
    const list = index.get(key);
    if (list) list.push(entry);
    else index.set(key, [entry]);
  });
  return index;
}

/**
 * Resolve a dependency model row to its remote volume entry, or null.
 * Exact folder wins, then the role's alias folders (unet/diffusion_models,
 * clip/text_encoders), then the first basename match.
 */
export function matchRemoteModel(model, remoteIndex) {
  if (!model || !remoteIndex || typeof remoteIndex.get !== "function") return null;
  const entries = remoteIndex.get(_remoteNameKey(model.filename));
  if (!entries || !entries.length) return null;
  const byFolder = (target) => entries.find(
    (e) => String(e.folder || "").trim().toLowerCase() === target
  );
  const folder = String(model.folder || "").trim().toLowerCase();
  if (folder) {
    const exact = byFolder(folder);
    if (exact) return exact;
  }
  for (const alias of _remoteFolderAliases(model.role)) {
    const hit = byFolder(alias);
    if (hit) return hit;
  }
  return entries[0];
}

/**
 * Copy a report model row with its remote availability projected on top.
 * A remote size > 0 upgrades a missing/unknown row to Installed; a remote
 * size of 0 stays missing. The local placeholder/path is preserved as
 * secondary detail only. Returns the original row when no remote entry
 * matches. Never mutates the input.
 */
export function overlayDependencyModel(model, remoteIndex) {
  if (!model || typeof model !== "object") return model;
  const remote = matchRemoteModel(model, remoteIndex);
  if (!remote) return model;
  const size = Number(remote.size);
  const available = Number.isFinite(size) && size > 0;
  const merged = Object.assign({}, model, {
    remote_model: {
      name: remote.name || model.filename || "",
      folder: remote.folder || "",
      size: Number.isFinite(size) ? size : 0,
    },
    remote_available: available,
  });
  // The report carries no local placement; the remote entry's annotation does.
  if (model.local_placeholder && typeof model.local_placeholder === "object") {
    merged.local_placeholder = model.local_placeholder;
  } else if (remote.local_placeholder && typeof remote.local_placeholder === "object") {
    merged.local_placeholder = remote.local_placeholder;
  }
  if (available && (merged.state === "missing" || merged.state === "unknown")) {
    merged.state = "installed";
    merged.installed = true;
  }
  return merged;
}

/**
 * Project a full dependency report through to the remote overlay, recomputing
 * the displayed summary (and therefore the "Download all" count) from the
 * overlay state. Returns a shallow copy; the input report is never mutated.
 * A null/absent index is a no-op so a failed remote read keeps local truth.
 */
export function overlayDependencyModels(deps, remoteIndex) {
  if (!deps || typeof deps !== "object" || !remoteIndex) return deps;
  const nodes = Array.isArray(deps.custom_nodes) ? deps.custom_nodes : [];
  const models = (Array.isArray(deps.models) ? deps.models : [])
    .map((m) => overlayDependencyModel(m, remoteIndex));
  const countModels = (state) => models.filter((m) => m && m.state === state).length;
  const countNodes = (state) => nodes.filter((n) => n && n.state === state).length;
  const installed = countModels("installed") + countNodes("installed");
  const missing = countModels("missing") + countNodes("missing");
  const wrong_version = countModels("wrong_version") + countNodes("wrong_revision");
  const unknown = countModels("unknown");
  const attention = missing + wrong_version + unknown;
  return Object.assign({}, deps, {
    models,
    summary: {
      installed,
      missing,
      wrong_version,
      unknown,
      attention,
      ready: attention === 0,
    },
  });
}

/** Human-readable byte size for the remote-availability detail line. */
function _formatRemoteSize(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let x = n;
  while (x >= 1024 && i < units.length - 1) { x /= 1024; i++; }
  return (i === 0 ? String(n) : x.toFixed(x >= 100 ? 0 : 1)) + " " + units[i];
}

/** Secondary detail for an installed row: remote size + local placeholder. */
function _remoteDetailText(m) {
  const parts = [];
  const size = _formatRemoteSize(m.remote_model && m.remote_model.size);
  if (size) parts.push("remote " + size);
  const lp = m.local_placeholder;
  if (lp && lp.is_placeholder) parts.push("local placeholder 0 B");
  else if (lp && lp.exists === false) parts.push("no local copy");
  return parts.join(" \u00b7 ");
}

/**
 * Render the version dependency section.
 * @param {object} version - selected workflow version (may carry
 *   dependency_metadata used as a fallback when the endpoint is unavailable)
 * @param {object|null} deps - GET .../dependencies payload or null (loading /
 *   failed / endpoint missing)
 * @param {function} [refreshHandler] - optional click handler for the Refresh
 *   button (data-testid="dependencies-refresh")
 * @param {object} [opts] - optional parity context:
 *   { apiBase } enables the explicit model install actions on missing rows;
 *   { managerModelsByFilename } supplies Manager catalog URLs/save paths when
 *   the library record has no source; { managerPacks } supplies the Manager
 *   pack index (CNR id / aux id / preemption / class / nodename_pattern) used
 *   to resolve a missing node's pack; { managerInstalled } supplies Manager's
 *   installed records (`{module, cnr_id, aux_id, enabled}`) for truthful
 *   installed/disabled states; { onInstallPack(node, plan) } optionally
 *   overrides the resolved Manager install (the wizard uses it to surface
 *   restart state); { onDepsRefresh } refreshes the owner's dependency report
 *   after an install; { onInstallSettled(model) } lets the owner drop its
 *   tracked in-flight status once a model install resolves truthfully;
 *   { onFindInLibrary(filename) } enables the contextual "Find in library"
 *   handoff on missing model rows.  Every action is user-click-only; nothing
 *   here installs or downloads automatically and nothing ever reboots.
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
    // Row + action key share one identity (key, else filename) so the wizard's
    // tracked in-flight status can always find the row it belongs to.
    "data-model-key": m.key || m.filename || "",
  });
  row.appendChild(_badge(m.role || "model", "role"));
  row.appendChild(el("span", { class: "comfymodal-studio-dependency-name", text: m.filename || "", title: m.filename || "" }));
  // The state badge is the single source of truth for install state; the
  // in-flight transition updates this same node in place (no "Not installed"
  // detail duplicate).
  const stateBadge = _stateBadgeFor(m.state);
  stateBadge.setAttribute("data-testid", "dependency-model-state");
  row.appendChild(stateBadge);
  if (m.state === "installed") {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-detail", text: m.local_path || m.folder || "" }));
    // Remote availability is secondary information: a nonempty remote volume
    // file is why the row reads Installed, and any local placeholder/path is
    // shown beside it rather than being mistaken for the model itself.
    const remoteDetail = _remoteDetailText(m);
    if (remoteDetail) {
      row.appendChild(el("span", {
        class: "comfymodal-studio-dependency-detail",
        "data-testid": "dependency-model-remote",
        title: (m.remote_model && m.remote_model.folder) ? ("remote volume folder: " + m.remote_model.folder) : "",
        text: remoteDetail,
      }));
    }
  } else {
    const src = m.source_urls && m.source_urls[0];
    if (src) {
      row.appendChild(el("a", { class: "comfymodal-studio-models-link", href: src, target: "_blank", rel: "noopener noreferrer", text: "source" }));
    }
    // Manager catalog fallback: per-filename download + page URLs when the
    // library record carries none. Path-like dependency filenames match the
    // catalog basename exactly.
    const managed = _managerModelFor(m, ctx);
    const managerUrl = managed && managed.url ? managed.url : "";
    const managerRef = managed && managed.reference ? managed.reference : "";
    if (managerRef && managerRef !== src) {
      row.appendChild(el("a", { class: "comfymodal-studio-models-link", href: managerRef, target: "_blank", rel: "noopener noreferrer", text: "manager source", title: (managed && managed.name) || m.filename }));
    }
    // Sourced rows keep exactly two install actions: async queue (install +
    // status polling) and sync single-item batch install. Source-less rows
    // get the explicit URL install control instead. All explicit-click only.
    const downloadUrl = src || managerUrl;
    const savePath = m.folder
      || (managed && normalizeManagerSavePath(managed.savePath, managed.type))
      || "";
    if (ctx && ctx.apiBase) {
      row.appendChild(renderModelInstallControls(m, downloadUrl, savePath, ctx, stateBadge));
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

// Explicit model install controls for a missing dependency row.
// Sourced rows keep the two existing actions: Queue install (async single
// install + status polling) and Install now (single-item synchronous batch).
// A source-less row gets an explicit URL input + install action so the user
// can supply a source; the URL is handed to the EXISTING backend install
// routes (validation/sanitization live there) and no model bytes are ever
// fetched in the browser. While an install is in flight the row's state badge
// shows "Downloading…" in place. Everything is explicit-click only.
function renderModelInstallControls(m, downloadUrl, savePath, ctx, stateBadge) {
  const wrap = el("span", { class: "comfymodal-studio-dependency-request" });
  const note = el("div", {
    class: "comfymodal-studio-dependency-request-note",
    "data-testid": "dependency-model-install-note",
    style: "display:none;font-size:10px;color:#888;margin-top:2px;",
  });
  const baseInfo = { filename: m.filename || "", url: downloadUrl || "", savePath: savePath || "" };
  const rowKey = m.key || m.filename || "";

  // In-flight truth: the SAME state badge transitions, then falls back to the
  // last-known state when the owner offers no refresh to re-evaluate it. A
  // queued (async) install reads "Queued for download"; a synchronous install
  // reads "Downloading…".
  const markQueued = () => applyDependencyInflightBadge(stateBadge, "queued", "Queued for download");
  const markDownloading = () => applyDependencyInflightBadge(stateBadge, "downloading", "Downloading\u2026");
  const restoreState = () => _applyStateBadge(stateBadge, m.state);
  const refreshDeps = async () => {
    if (typeof ctx.onDepsRefresh === "function") {
      try { await ctx.onDepsRefresh(); return true; } catch (e) { /* refresh is best-effort */ }
    }
    return false;
  };
  // The owner reconciles its tracked status once the install has settled so a
  // successful install never leaves a stale pseudo-badge behind.
  const settle = () => {
    if (typeof ctx.onInstallSettled === "function") ctx.onInstallSettled(m);
  };

  // No library/Manager source: explicit user-supplied URL. The backend route
  // validates and sanitizes it and downloads into the Modal workspace/volume;
  // the browser never receives the model bytes.
  if (!downloadUrl) {
    const urlIn = el("input", {
      type: "text",
      class: "comfymodal-studio-wf-input",
      "data-testid": "dependency-model-url-input",
      "aria-label": "Model source URL for " + (m.filename || "model"),
      placeholder: "https://\u2026",
      style: "font-size:10px;padding:2px 6px;width:220px;",
    });
    const urlBtn = el("button", {
      class: "comfymodal-secondary-btn",
      type: "button",
      "data-testid": "dependency-model-url-install",
      "data-model-key": rowKey,
      text: "Install from URL",
      style: "font-size:10px;padding:2px 8px;width:auto;",
      onclick: async () => {
        if (urlBtn.disabled) return; // dedupe while in flight
        const url = (urlIn.value || "").trim();
        if (!url) {
          note.style.display = "block";
          note.textContent = "Paste a model URL first.";
          note.classList.add("error");
          return;
        }
        urlBtn.disabled = true;
        urlBtn.textContent = "Installing\u2026";
        note.style.display = "block";
        note.textContent = "Starting install\u2026";
        note.classList.remove("error");
        markDownloading();
        const res = await queueModelInstall(ctx.apiBase, {
          url: url,
          filename: baseInfo.filename,
          savePath: baseInfo.savePath,
        });
        note.textContent = res.message;
        note.classList.toggle("error", !res.ok);
        if (res.ok) {
          if (!(await refreshDeps())) restoreState();
          settle();
        } else {
          restoreState();
          urlBtn.disabled = false;
          urlBtn.textContent = "Install from URL";
        }
      },
    });
    wrap.appendChild(urlIn);
    wrap.appendChild(urlBtn);
    wrap.appendChild(note);
    return wrap;
  }

  const info = baseInfo;

  const queueBtn = el("button", {
    class: "comfymodal-secondary-btn",
    type: "button",
    "data-testid": "dependency-model-queue",
    "data-model-key": rowKey,
    text: "Queue install",
    style: "font-size:10px;padding:2px 8px;width:auto;",
    onclick: async () => {
      if (queueBtn.disabled) return; // dedupe while in flight
      queueBtn.disabled = true;
      queueBtn.textContent = "Queueing\u2026";
      note.style.display = "block";
      note.textContent = "Starting install\u2026";
      note.classList.remove("error");
      markQueued();
      const res = await queueModelInstall(ctx.apiBase, info);
      note.textContent = res.message;
      note.classList.toggle("error", !res.ok);
      if (res.ok) {
        if (!(await refreshDeps())) restoreState();
        settle();
      } else {
        restoreState();
        queueBtn.disabled = false;
        queueBtn.textContent = "Queue install";
      }
    },
  });

  const nowBtn = el("button", {
    class: "comfymodal-secondary-btn",
    type: "button",
    "data-testid": "dependency-model-install-now",
    "data-model-key": rowKey,
    text: "Install now",
    style: "font-size:10px;padding:2px 8px;width:auto;",
    onclick: async () => {
      if (nowBtn.disabled) return; // dedupe while in flight
      nowBtn.disabled = true;
      nowBtn.textContent = "Installing\u2026";
      note.style.display = "block";
      note.textContent = "Installing\u2026";
      note.classList.remove("error");
      markDownloading();
      const res = await installModelNow(ctx.apiBase, info);
      note.textContent = res.message;
      note.classList.toggle("error", !res.ok);
      if (res.ok) {
        if (!(await refreshDeps())) restoreState();
        settle();
      } else {
        restoreState();
        nowBtn.disabled = false;
        nowBtn.textContent = "Install now";
      }
    },
  });

  wrap.appendChild(queueBtn);
  wrap.appendChild(nowBtn);
  wrap.appendChild(note);
  return wrap;
}

/** Async single model install + status poll. Explicit click only. */
async function queueModelInstall(apiBase, info) {
  try {
    const started = await installSingleModel(apiBase, {
      url: info.url, filename: info.filename, save_path: info.savePath || "",
    });
    const downloadId = started && (started.download_id || (started.data && started.data.download_id));
    if (!downloadId) {
      return { ok: false, message: "Install request failed: " + ((started && started.message) || "request failed") };
    }
    const deadline = Date.now() + 10 * 60 * 1000;
    for (;;) {
      const st = await modelDownloadStatus(apiBase, downloadId);
      const last = (st && (st.data || st)) || {};
      const s = String(last.state || last.status || "").toLowerCase();
      if (s === "complete" || s === "done" || s === "success") break;
      if (s === "error" || s === "failed") {
        return { ok: false, message: "Install failed: " + (last.message || last.error || "request failed") };
      }
      if (Date.now() > deadline) {
        return { ok: false, message: "Install timed out \u2014 check the Model Library later." };
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
    try { await rescanModels(apiBase, false); } catch (e) { /* rescan is best-effort */ }
    return { ok: true, message: "Downloaded \u2014 Model Library rescanned." };
  } catch (err) {
    return { ok: false, message: "Install failed: " + ((err && err.message) || "request failed") };
  }
}

/** Synchronous single-item batch install (same route as the bulk action). */
async function installModelNow(apiBase, info) {
  try {
    const resp = await batchInstallModels(apiBase, [{
      url: info.url, filename: info.filename, save_path: info.savePath || "",
    }]);
    if (!resp || resp.status !== "ok") {
      return { ok: false, message: "Install failed: " + ((resp && (resp.message || resp.error)) || "request failed") };
    }
    try { await rescanModels(apiBase, false); } catch (e) { /* rescan is best-effort */ }
    return { ok: true, message: "Installed \u2014 Model Library rescanned." };
  } catch (err) {
    return { ok: false, message: "Install failed: " + ((err && err.message) || "request failed") };
  }
}

/**
 * Pure: normalize Manager's `/customnode/installed` payload into the
 * `{ module, ver, cnr_id, aux_id, enabled }` list the dependency rows match
 * against. The endpoint returns a dict keyed by module name; `enabled=false`
 * is preserved so a disabled pack is never reported ready. A list shape is
 * tolerated as-is without inventing fields.
 */
export function parseManagerInstalled(data) {
  const records = [];
  if (data && typeof data === "object" && !Array.isArray(data)) {
    Object.keys(data).forEach((module) => {
      const info = data[module];
      if (!info || typeof info !== "object" || Array.isArray(info)) return;
      records.push({
        module: module,
        ver: info.ver || "",
        cnr_id: info.cnr_id || "",
        aux_id: info.aux_id || "",
        enabled: !(info.enabled === false || String(info.enabled).toLowerCase() === "false"),
      });
    });
  } else if (Array.isArray(data)) {
    data.forEach((info) => {
      if (info && typeof info === "object") records.push(info);
    });
  }
  return records;
}

/**
 * Match a missing node against Manager's `/customnode/installed` records.
 * The endpoint returns a dict keyed by module name with
 * `{ ver, cnr_id, aux_id, enabled }` values; matching is by CNR id, aux id
 * (full or basename), module name, or repository. Never assumes installed.
 */
function _installedRecordFor(n, ctx) {
  const records = Array.isArray(ctx && ctx.managerInstalled) ? ctx.managerInstalled : [];
  if (!records.length || !n) return null;
  const lower = (v) => String(v == null ? "" : v).trim().toLowerCase();
  const cnr = lower(n.cnr_id);
  const aux = lower(n.aux_id);
  const auxBase = _basename(aux);
  const name = lower(n.name);
  const repo = lower(n.repository_url);
  for (const record of records) {
    if (!record || typeof record !== "object") continue;
    const recCnr = lower(record.cnr_id);
    const recAux = lower(record.aux_id);
    const recModule = lower(record.module || record.name);
    if (cnr && recCnr && recCnr === cnr) return record;
    if (aux && (recAux === aux || (auxBase && recAux === auxBase) || recModule === aux)) {
      return record;
    }
    if (name && recModule && recModule === name) return record;
    if (repo && recModule && recModule === repo) return record;
  }
  return null;
}

/**
 * True only with an explicit loaded-class proof for every one of the node's
 * required classes (e.g. a caller that probed ComfyUI's live node registry).
 * Manager's `/customnode/installed` dict is NOT proof: a package can be on
 * disk yet its classes never loaded. When absent, resolver state is authority.
 */
function _hasLoadedClassProof(n, ctx) {
  const loaded = ctx && ctx.loadedClasses;
  if (!loaded || !n) return false;
  const classes = Array.isArray(n.classes) ? n.classes : (n.classes ? [n.classes] : []);
  if (!classes.length) return false;
  const has = (cls) => {
    if (loaded instanceof Set) return loaded.has(cls);
    if (Array.isArray(loaded)) return loaded.indexOf(cls) !== -1;
    return false;
  };
  return classes.every((cls) => has(String(cls)));
}

function renderDependencyNodeRow(n, ctx) {
  // Resolve before rendering: a missing row may be identified by CNR id,
  // aux id, or class against the Manager catalog. Never invent a URL.
  const plan = n.state === "missing"
    ? resolveNodeInstall(n, ctx && ctx.managerPacks)
    : { kind: "none" };
  const node = plan.pack
    ? Object.assign({}, n, {
        repository_url: plan.pack.repository_url || n.repository_url || "",
        name: plan.pack.name || n.name || n.cnr_id || n.aux_id || "",
      })
    : n;
  const displayName = node.name || "";
  const row = el("div", {
    class: "comfymodal-studio-dependency-row",
    "data-testid": "dependency-node-row",
    "data-node-name": displayName,
  });
  row.appendChild(el("span", { class: "comfymodal-studio-dependency-name", text: displayName, title: displayName }));
  const nodeBadge = _stateBadgeFor(node.state);
  nodeBadge.setAttribute("data-testid", "dependency-node-state");
  row.appendChild(nodeBadge);
  row.appendChild(el("span", {
    class: "comfymodal-studio-dependency-detail",
    text: node.installed_commit ? _shortCommit(node.installed_commit) : "",
    title: node.installed_commit || "",
  }));
  if (node.required_revision) {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-detail", text: "required " + node.required_revision }));
  }
  if (node.install_path) {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-path", text: node.install_path, title: node.install_path }));
  }
  if (node.repository_url) {
    row.appendChild(el("a", { class: "comfymodal-studio-models-link", href: node.repository_url, target: "_blank", rel: "noopener noreferrer", text: "repo" }));
  }
  // Missing pack: the resolver is authoritative. Manager's installed dict is
  // only advisory — it never proves the classes loaded, so it never hides the
  // single install action nor reports "Installed". A loaded-class proof (live
  // registry) is the only thing that can upgrade a resolver-missing row.
  // Never auto-installs or auto-reboots.
  if (node.state === "missing") {
    const installedRecord = _installedRecordFor(n, ctx);
    if (_hasLoadedClassProof(node, ctx)) {
      row.appendChild(el("span", {
        class: "comfymodal-studio-dependency-detail",
        "data-testid": "dependency-node-loaded",
        text: "Installed (required classes loaded)",
      }));
    } else {
      if (installedRecord) {
        const enabled = installedRecord.enabled !== false;
        row.appendChild(el("span", {
          class: "comfymodal-studio-dependency-detail",
          "data-testid": "dependency-node-manager-stale",
          text: enabled
            ? "Manager package present, but required classes are not loaded"
            : "Manager package present but disabled — required classes are not loaded",
        }));
      }
      if (plan.kind === "none") {
        row.appendChild(el("span", {
          class: "comfymodal-studio-dependency-detail",
          "data-testid": "dependency-node-no-target",
          text: "No Manager install target identified \u2014 install manually.",
        }));
      } else {
        row.appendChild(renderNodeInstallNowControl(node, plan, ctx, nodeBadge));
      }
    }
  }
  return row;
}

// The single Manager-backed install action for a missing custom-node pack.
// The owner (wizard) may override it to capture restart state; otherwise the
// row performs the resolved plan directly. Explicit click only. The row's own
// missing badge reads "Queued" while the install is in flight, then returns to
// the report's real state so it never lies.
function renderNodeInstallNowControl(n, installPlan, ctx, nodeBadge) {
  const c = ctx || {};
  const wrap = el("span", { class: "comfymodal-studio-dependency-request" });
  const note = el("div", {
    class: "comfymodal-studio-dependency-request-note",
    "data-testid": "dependency-node-install-note",
    style: "display:none;font-size:10px;color:#888;margin-top:2px;",
  });
  const restoreState = () => applyDependencyStateBadge(nodeBadge, n.state);
  const btn = el("button", {
    class: "comfymodal-secondary-btn",
    type: "button",
    "data-testid": "dependency-node-install-now",
    "data-node-name": n.name || "",
    text: (c.installingPack && c.installingPack === n.name) ? "Installing\u2026" : "Install now",
    style: "font-size:10px;padding:2px 8px;width:auto;",
    onclick: async () => {
      if (btn.disabled) return; // dedupe while in flight
      if (typeof c.onInstallPack === "function") {
        // Owner-managed install (wizard): it re-renders with restart state.
        c.onInstallPack(n, installPlan);
        return;
      }
      btn.disabled = true;
      btn.textContent = "Installing\u2026";
      note.style.display = "block";
      note.textContent = "Installing\u2026";
      note.classList.remove("error");
      applyDependencyInflightBadge(nodeBadge, "queued", "Queued");
      const res = await performManagerInstall(installPlan);
      note.textContent = res.message;
      note.classList.toggle("error", !res.ok);
      // Report truth on completion: the row is missing until the resolver says
      // otherwise, so a settled install never leaves a stale "Queued" badge.
      restoreState();
      if (!res.ok) {
        btn.disabled = false;
        btn.textContent = "Install now";
      }
    },
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
