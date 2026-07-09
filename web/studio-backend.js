// Modal Studio — Backend
//
// Backend page with two-pane layout: left list, right detail/editor.
// Studio backend abstraction fields: { id, label, description, compatibleFeatures,
// sourceType, sourceId, workflowId, modelLabel, modelTriple, loras, defaults,
// disabledReason, archived }
// Exports helpers for Playground compare-backends integration.
//
// Empty state: suggests creating from existing legacy profile/preset or
// opening Settings > Legacy > Profiles.

let _backendCache = null;
let _selectedBackendId = null;

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    } else if (k === "value") {
      e.value = props[k];
    } else {
      e.setAttribute(k, props[k]);
    }
  }
  for (const c of (Array.isArray(children) ? children : [children])) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

export async function getBackends(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const res = await fetch(`${apiBase}/studio/backends`);
    if (!res.ok) return [];
    const data = await res.json();
    _backendCache = (data && data.backends) || [];
    return _backendCache;
  } catch {
    return [];
  }
}

export async function getCompareBackends(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const res = await fetch(`${apiBase}/studio/backends?kind=comparable`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data && data.backends) || [];
  } catch {
    return [];
  }
}

export function renderBackend(state, context) {
  const container = el("div", {
    class: "comfymodal-studio-backend",
    "data-testid": "backend-page",
  });

  // ── Left: Backend List ──────────────────────────────────────
  const listPanel = el("div", {
    class: "comfymodal-studio-backend-list",
    "data-testid": "backend-list",
  });

  const listHeader = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;" }, [
    el("h3", {
      text: "Backends",
      style: "margin:0;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;",
    }),
    el("button", {
      class: "comfymodal-secondary-btn",
      text: "+ New",
      style: "font-size:10px;padding:3px 8px;",
      onclick: () => createNewBackend(state, context, listPanel, detailPanel),
    }),
  ]);
  listPanel.appendChild(listHeader);

  const listContent = el("div", { style: "flex:1;overflow-y:auto;" });
  listPanel.appendChild(listContent);

  // ── Right: Detail/Editor ────────────────────────────────────
  const detailPanel = el("div", {
    class: "comfymodal-studio-backend-detail",
    "data-testid": "backend-detail",
  });

  container.appendChild(listPanel);
  container.appendChild(detailPanel);

  // Loading state
  listContent.textContent = "Loading backends...";

  // Fetch and render
  getBackends(context).then((backends) => {
    while (listContent.firstChild) listContent.removeChild(listContent.firstChild);

    if (!backends || backends.length === 0) {
      renderEmptyState(listContent, detailPanel, context, state);
      return;
    }

    renderBackendList(listContent, backends, context, detailPanel, state);

    // Select first backend by default
    if (backends.length > 0 && !_selectedBackendId) {
      _selectedBackendId = backends[0].id || backends[0].label;
      renderBackendDetail(detailPanel, backends[0], context, listContent);
    }
    // Highlight first card
    const firstCard = listContent.querySelector(".comfymodal-studio-backend-card");
    if (firstCard) firstCard.classList.add("active");
  });

  return container;
}

function renderEmptyState(listContent, detailPanel, context, state) {
  const emptyCard = el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No backends configured yet.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: "Create a new backend or import from legacy profiles.", style: "font-size:12px;color:#555;margin:0 0 8px;" }),
    el("a", {
      text: "Open Legacy Profiles",
      style: "color:#dc2626;cursor:pointer;font-size:12px;",
      onclick: (e) => {
        e.preventDefault();
        if (context && context.setPage) {
          if (state && state.settings) {
            state.settings.activeLegacyTab = "profiles";
          }
          context.setPage("settings");
        }
      },
    }),
  ]);
  listContent.appendChild(emptyCard);

  // Show create form in detail panel
  const newForm = renderBackendForm(null, context, listContent, detailPanel);
  detailPanel.appendChild(newForm);
}

function renderBackendList(container, backends, context, detailPanel, state) {
  while (container.firstChild) container.removeChild(container.firstChild);

  backends.forEach((backend) => {
    const id = backend.id || backend.label || "unknown";
    const isActive = _selectedBackendId === id;

    const card = el("div", {
      class: `comfymodal-studio-backend-card${isActive ? " active" : ""}`,
      onclick: () => {
        _selectedBackendId = id;
        // Update active state
        container.querySelectorAll(".comfymodal-studio-backend-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        // Render detail
        while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
        renderBackendDetail(detailPanel, backend, context, container);
      },
    }, [
      el("h4", { text: backend.label || backend.id || "Unnamed" }),
      el("p", { text: backend.description || backend.sourceType || (backend.compatibleFeatures || []).join(", ") || "No description" }),
    ]);
    container.appendChild(card);
  });
}

function renderBackendDetail(container, backend, context, listContainer) {
  while (container.firstChild) container.removeChild(container.firstChild);

  const detailCard = el("div", { class: "comfymodal-studio-backend-detail-card" });

  // ── Editable fields ─────────────────────────────────────
  const fields = [
    { key: "label", label: "Label", type: "text", value: backend.label || "" },
    { key: "description", label: "Description", type: "textarea", value: backend.description || "" },
    { key: "sourceType", label: "Source Type", type: "text", value: backend.sourceType || "" },
    { key: "sourceId", label: "Source ID", type: "text", value: backend.sourceId || "" },
    { key: "workflowId", label: "Workflow ID", type: "text", value: backend.workflowId || "" },
    { key: "modelLabel", label: "Model Label", type: "text", value: backend.modelLabel || "" },
    { key: "modelTriple", label: "Model Triple", type: "text", value: backend.modelTriple || "" },
    { key: "disabledReason", label: "Disabled Reason", type: "text", value: backend.disabledReason || "" },
  ];

  const fieldValues = {};

  fields.forEach((f) => {
    const fieldGroup = el("div", { class: "comfymodal-studio-backend-field" });
    const label = el("label", { text: f.label });
    fieldGroup.appendChild(label);

    let input;
    if (f.type === "textarea") {
      input = el("textarea", { value: f.value, rows: 2 });
    } else {
      input = el("input", { type: "text", value: f.value });
    }
    input.addEventListener("input", () => { fieldValues[f.key] = input.value; });
    fieldGroup.appendChild(input);
    detailCard.appendChild(fieldGroup);
    fieldValues[f.key] = f.value;
  });

  // ── Feature Compatibility Checkboxes ─────────────────────
  const compatGroup = el("div", { class: "comfymodal-studio-backend-field" });
  const compatLabel = el("label", { text: "Compatible Features" });
  compatGroup.appendChild(compatLabel);

  const compatFeatures = backend.compatibleFeatures || [];
  ["txt2img", "object_remove", "object_replace"].forEach((feature) => {
    const cbLabel = el("label", { style: "display:flex;align-items:center;gap:4px;font-size:11px;margin:2px 0;color:#888;" });
    const cb = el("input", { type: "checkbox" });
    cb.checked = compatFeatures.includes(feature);
    cb.addEventListener("change", () => {
      fieldValues.compatibleFeatures = fieldValues.compatibleFeatures || [...compatFeatures];
      if (cb.checked) {
        if (!fieldValues.compatibleFeatures.includes(feature)) {
          fieldValues.compatibleFeatures.push(feature);
        }
      } else {
        fieldValues.compatibleFeatures = fieldValues.compatibleFeatures.filter((f) => f !== feature);
      }
    });
    cbLabel.appendChild(cb);
    cbLabel.appendChild(document.createTextNode(feature === "txt2img" ? "Txt2Img" : feature === "object_remove" ? "Object Remove" : "Object Replace"));
    compatGroup.appendChild(cbLabel);
  });
  if (!compatFeatures.length) {
    const note = el("p", { text: "None selected", style: "font-size:11px;color:#555;margin:2px 0;" });
    compatGroup.appendChild(note);
  }
  detailCard.appendChild(compatGroup);

  // ── LoRA list ──────────────────────────────────────────
  const loraGroup = el("div", { class: "comfymodal-studio-backend-field" });
  const loraLabel = el("label", { text: "LoRAs" });
  loraGroup.appendChild(loraLabel);
  const loraText = el("p", {
    text: (backend.loras && backend.loras.length > 0)
      ? backend.loras.map((l) => l.name || l).join(", ")
      : "None configured",
    style: "font-size:11px;color:#555;",
  });
  loraGroup.appendChild(loraText);
  detailCard.appendChild(loraGroup);

  // ── Archival status ────────────────────────────────────
  if (backend.archived) {
    const archivedNote = el("p", {
      text: "\u26a0 Archived",
      style: "font-size:11px;color:#dc2626;margin:4px 0;",
    });
    detailCard.appendChild(archivedNote);
  }

  // ── Action buttons ─────────────────────────────────────
  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  const saveBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Save",
    style: "width:auto;padding:5px 16px;",
    onclick: async () => {
      const apiBase = (context && context.apiBase) || "/comfymodal";
      try {
        // Align payload with backend PATCH route: name + studio_metadata
        const studioMeta = { ...fieldValues };
        if (!studioMeta.compatibleFeatures) studioMeta.compatibleFeatures = compatFeatures;
        delete studioMeta.name; // name is stored at top level
        const payload = {
          name: fieldValues.label || backend.label || backend.id || "",
          studio_metadata: studioMeta,
          disabled_reason: fieldValues.disabledReason || backend.disabledReason || "",
        };
        const res = await fetch(
          `${apiBase}/studio/backends/${encodeURIComponent(backend.id || backend.label)}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          }
        );
        if (res.ok) {
          _backendCache = null;
          const fresh = await getBackends(context);
          renderBackendList(listContainer, fresh, context, container, {});
          if (fresh.length > 0) {
            _selectedBackendId = fresh[0].id || fresh[0].label;
            renderBackendDetail(container, fresh[0], context, listContainer);
          }
        }
      } catch {
        // silent
      }
    },
  });
  actions.appendChild(saveBtn);

  const duplicateBtn = el("button", {
    class: "comfymodal-secondary-btn",
    text: "Duplicate",
    style: "font-size:10px;padding:5px 12px;",
    onclick: async () => {
      const apiBase = (context && context.apiBase) || "/comfymodal";
      try {
        const res = await fetch(
          `${apiBase}/studio/backends/${encodeURIComponent(backend.id || backend.label)}/duplicate`,
          { method: "POST" }
        );
        if (res.ok) {
          _backendCache = null;
          const fresh = await getBackends(context);
          renderBackendList(listContainer, fresh, context, container, {});
          if (fresh.length > 0) {
            _selectedBackendId = fresh[0].id || fresh[0].label;
            renderBackendDetail(container, fresh[0], context, listContainer);
          }
        }
      } catch {
        // silent
      }
    },
  });
  actions.appendChild(duplicateBtn);

  if (!backend.archived) {
    const archiveBtn = el("button", {
      class: "comfymodal-destructive-btn",
      text: "Archive",
      style: "font-size:10px;padding:5px 12px;",
      onclick: async () => {
        const apiBase = (context && context.apiBase) || "/comfymodal";
        try {
          const res = await fetch(
            `${apiBase}/studio/backends/${encodeURIComponent(backend.id || backend.label)}`,
            { method: "DELETE" }
          );
          if (res.ok) {
            _backendCache = null;
            _selectedBackendId = null;
            const fresh = await getBackends(context);
            // Re-render list
            const parentList = listContainer.closest(".comfymodal-studio-backend")?.querySelector(".comfymodal-studio-backend-list > div:last-child");
            if (parentList) {
              // Full re-render
              while (listContainer.firstChild) listContainer.removeChild(listContainer.firstChild);
              while (container.firstChild) container.removeChild(container.firstChild);
              if (fresh.length === 0) {
                renderEmptyState(listContainer, container, context);
              } else {
                renderBackendList(listContainer, fresh, context, container, {});
                _selectedBackendId = fresh[0].id || fresh[0].label;
                renderBackendDetail(container, fresh[0], context, listContainer);
              }
            }
          }
        } catch {
          // silent
        }
      },
    });
    actions.appendChild(archiveBtn);
  }

  detailCard.appendChild(actions);
  container.appendChild(detailCard);
}

function renderBackendForm(existing, context, listContainer, detailPanel) {
  const formCard = el("div", { class: "comfymodal-studio-backend-detail-card" });

  const heading = el("h4", {
    text: existing ? "Edit Backend" : "New Backend",
    style: "margin:0 0 12px;font-size:12px;color:#d0d0d0;text-transform:uppercase;letter-spacing:0.05em;",
  });
  formCard.appendChild(heading);

  const fields = [
    { key: "label", label: "Label", type: "text" },
    { key: "description", label: "Description", type: "textarea" },
    { key: "sourceType", label: "Source Type", type: "text" },
    { key: "workflowId", label: "Workflow ID", type: "text" },
    { key: "modelLabel", label: "Model Label", type: "text" },
  ];

  const fieldValues = {};
  fields.forEach((f) => {
    const fieldGroup = el("div", { class: "comfymodal-studio-backend-field" });
    const label = el("label", { text: f.label });
    fieldGroup.appendChild(label);
    let input;
    if (f.type === "textarea") {
      input = el("textarea", { rows: 2 });
    } else {
      input = el("input", { type: "text" });
    }
    input.addEventListener("input", () => { fieldValues[f.key] = input.value; });
    fieldGroup.appendChild(input);
    formCard.appendChild(fieldGroup);
    fieldValues[f.key] = "";
  });

  const compatGroup = el("div", { class: "comfymodal-studio-backend-field" });
  const compatLabel = el("label", { text: "Compatible Features" });
  compatGroup.appendChild(compatLabel);
  const compatFeatures = [];
  ["txt2img", "object_remove", "object_replace"].forEach((feature) => {
    const cbLabel = el("label", { style: "display:flex;align-items:center;gap:4px;font-size:11px;margin:2px 0;color:#888;" });
    const cb = el("input", { type: "checkbox" });
    cb.addEventListener("change", () => {
      if (cb.checked) {
        if (!compatFeatures.includes(feature)) compatFeatures.push(feature);
      } else {
        const idx = compatFeatures.indexOf(feature);
        if (idx > -1) compatFeatures.splice(idx, 1);
      }
    });
    cbLabel.appendChild(cb);
    cbLabel.appendChild(document.createTextNode(feature === "txt2img" ? "Txt2Img" : feature === "object_remove" ? "Object Remove" : "Object Replace"));
    compatGroup.appendChild(cbLabel);
  });
  formCard.appendChild(compatGroup);

  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  const createBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Create",
    style: "width:auto;padding:5px 16px;",
    onclick: async () => {
      const apiBase = (context && context.apiBase) || "/comfymodal";
      try {
        // Align create payload with backend POST route: name + studio_metadata
        const studioMeta = { ...fieldValues, compatibleFeatures: compatFeatures };
        const payload = {
          name: fieldValues.label || "New Backend",
          studio_metadata: studioMeta,
        };
        const res = await fetch(`${apiBase}/studio/backends`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          _backendCache = null;
          const fresh = await getBackends(context);
          // Re-render the whole page
          while (listContainer.firstChild) listContainer.removeChild(listContainer.firstChild);
          while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
          if (fresh.length === 0) {
            renderEmptyState(listContainer, detailPanel, context);
          } else {
            renderBackendList(listContainer, fresh, context, detailPanel, {});
            _selectedBackendId = fresh[0].id || fresh[0].label;
            renderBackendDetail(detailPanel, fresh[0], context, listContainer);
          }
        }
      } catch {
        // silent
      }
    },
  });
  actions.appendChild(createBtn);

  formCard.appendChild(actions);
  return formCard;
}

function createNewBackend(state, context, listPanel, detailPanel) {
  while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
  const parentContainer = listPanel.closest(".comfymodal-studio-backend")
    ? listPanel.closest(".comfymodal-studio-backend").querySelector(".comfymodal-studio-backend-detail")
    : detailPanel;
  const form = renderBackendForm(null, context, listPanel, parentContainer || detailPanel);
  (parentContainer || detailPanel).appendChild(form);
}
