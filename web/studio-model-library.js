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

import { el } from "./studio-ui.js";
import {
  listModels,
  listModelTypes,
  listCustomNodes,
  rescanModels,
  updateModel,
  requestModelInstall,
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

// Badge for library rows and dependency rows.
function _badge(text, kind) {
  return el("span", { class: "comfymodal-studio-model-badge " + kind, text: text });
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

  // First open: kick off the initial data load.
  if (!md._loaded && !md.loading) {
    md.loading = true;
    loadModelsData(apiBase, view, refresh);
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
      el("h3", { text: "Model Library" }),
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
    list.appendChild(el("div", { class: "comfymodal-studio-models-empty", text: "Loading models\u2026" }));
  } else if (md.scanHint === "not_scanned" && md.models.length === 0) {
    list.appendChild(el("div", { class: "comfymodal-studio-models-empty", text: "No models scanned yet. Click Scan models." }));
  } else if (md.models.length === 0) {
    list.appendChild(el("div", { class: "comfymodal-studio-models-empty", text: "No models match your filters." }));
  } else {
    md.models.forEach((m) => list.appendChild(renderModelRow(m, apiBase, view, refresh)));
  }
  root.appendChild(list);

  return root;

  // ── Internal async handlers (closure-scoped) ────────────────────────────

  async function handleRescan(apiBaseRef, viewRef, refreshRef, btn, rehashInput) {
    btn.disabled = true;
    btn.textContent = "Scanning\u2026";
    const resp = await rescanModels(apiBaseRef, rehashInput.checked);
    const summary = resp && resp.summary ? resp.summary : null;
    const total = summary ? summary.total : null;
    rescanStatus.style.display = "block";
    if (resp && resp.status === "ok") {
      rescanStatus.textContent = summary
        ? "Scan complete \u2014 " + total + " model" + (total === 1 ? "" : "s") + " total."
        : "Scan complete.";
      rescanStatus.classList.remove("error");
    } else {
      rescanStatus.textContent = "Scan failed: " + ((resp && resp.message) || "request failed");
      rescanStatus.classList.add("error");
    }
    btn.disabled = false;
    btn.textContent = "Scan models";
    if (viewRef.modelsData) viewRef.modelsData.scanHint = "ok";
    await reloadModelsList(apiBaseRef, viewRef, refreshRef);
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

function renderModelRow(m, apiBase, view, refresh) {
  const row = el("div", {
    class: "comfymodal-studio-model-row",
    "data-testid": "model-row",
    "data-model-id": m.model_id,
  });
  row.appendChild(el("div", { class: "comfymodal-studio-model-main" }, [
    el("span", { class: "comfymodal-studio-model-name", text: m.display_name || m.filename || "" }),
    el("span", { class: "comfymodal-studio-model-file", text: m.filename || "" }),
  ]));
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
 * @returns {HTMLElement}
 */
export function renderDependencySection(version, deps, refreshHandler) {
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
        el("div", { class: "comfymodal-studio-dependency-table" }, models.map(renderDependencyModelRow)),
      ]));
    }
    if (nodes.length) {
      section.appendChild(el("div", { class: "comfymodal-studio-dependency-group", "data-testid": "dependency-nodes" }, [
        el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Custom nodes" }),
        el("div", { class: "comfymodal-studio-dependency-table" }, nodes.map(renderDependencyNodeRow)),
      ]));
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
        stack.map((m) => el("span", { class: "comfymodal-studio-wf-chip", text: m }))),
    ]));
  }
  if (classes.length) {
    wrap.appendChild(el("div", { class: "comfymodal-studio-dependencies-group" }, [
      el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Node classes" }),
      el("div", { class: "comfymodal-studio-dependencies-chips" },
        classes.map((c) => el("span", { class: "comfymodal-studio-wf-chip", text: c }))),
    ]));
  }
  return wrap;
}

function renderDependencyModelRow(m) {
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
  }
  return row;
}

function renderDependencyNodeRow(n) {
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
  if (n.install_path) {
    row.appendChild(el("span", { class: "comfymodal-studio-dependency-path", text: n.install_path, title: n.install_path }));
  }
  if (n.repository_url) {
    row.appendChild(el("a", { class: "comfymodal-studio-models-link", href: n.repository_url, target: "_blank", rel: "noopener noreferrer", text: "repo" }));
  }
  return row;
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
