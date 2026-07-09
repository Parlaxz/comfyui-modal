import { app } from "../../scripts/app.js";

const SLOT_KEYS = ["prompt", "negative_prompt", "seed", "steps", "guidance", "width", "height", "input_image"];

const LOADER_FIELDS = [
  { classType: "CheckpointLoaderSimple", field: "ckpt_name", label: "Checkpoint" },
  { classType: "CheckpointLoader", field: "ckpt_name", label: "Checkpoint" },
  { classType: "UNETLoader", field: "unet_name", label: "UNet" },
  { classType: "CLIPLoader", field: "clip_name", label: "CLIP" },
  { classType: "DualCLIPLoader", field: "clip_name1", label: "CLIP 1" },
  { classType: "DualCLIPLoader", field: "clip_name2", label: "CLIP 2" },
  { classType: "TripleCLIPLoader", field: "clip_name1", label: "CLIP 1" },
  { classType: "TripleCLIPLoader", field: "clip_name2", label: "CLIP 2" },
  { classType: "TripleCLIPLoader", field: "clip_name3", label: "CLIP 3" },
  { classType: "VAELoader", field: "vae_name", label: "VAE" },
];

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k === "html") e.innerHTML = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    else if (k === "value") e.value = props[k];
    else if (k === "checked") e.checked = !!props[k];
    else e.setAttribute(k, props[k]);
  }
  for (const c of (Array.isArray(children) ? children : [children])) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

async function fetchJson(path, options = {}) {
  const res = await fetch(path, options);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!res.ok) throw new Error((data && data.message) || `HTTP ${res.status}`);
  return data;
}

function statusBadge(status) {
  const cls = status === "ready"
    ? "success"
    : status === "needs_mapping"
      ? "warning"
      : "danger";
  return el("span", { class: `comfymodal-status-badge ${cls}`, text: status || "unknown" });
}

function normalizationBadge(profile) {
  const norm = profile && profile.t2i_normalization;
  if (norm && norm !== "legacy") {
    return el("span", { class: "comfymodal-mode-badge norm", text: norm });
  }
  return el("span", { class: "comfymodal-mode-badge legacy", text: "Legacy T2I" });
}

function modelStackSummary(modelStack = {}) {
  const parts = [];
  if (modelStack.checkpoint && modelStack.checkpoint.length) parts.push(`CKPT: ${modelStack.checkpoint[0]}`);
  if (modelStack.unet && modelStack.unet.length) parts.push(`UNet: ${modelStack.unet[0]}`);
  if (modelStack.clip && modelStack.clip.length) parts.push(`CLIP: ${modelStack.clip.join(" / ")}`);
  if (modelStack.vae && modelStack.vae.length) parts.push(`VAE: ${modelStack.vae[0]}`);
  return parts.join(" · ") || "No model triple detected";
}

function clone(obj) {
  return JSON.parse(JSON.stringify(obj || {}));
}

function extractLoaderRows(workflowApi = {}) {
  const rows = [];
  for (const [nodeId, node] of Object.entries(workflowApi || {})) {
    if (!node || typeof node !== "object") continue;
    const classType = node.class_type || "";
    const inputs = node.inputs || {};
    for (const spec of LOADER_FIELDS) {
      if (spec.classType !== classType) continue;
      rows.push({
        nodeId,
        classType,
        field: spec.field,
        label: spec.label,
        value: typeof inputs[spec.field] === "string" ? inputs[spec.field] : "",
      });
    }
  }
  return rows;
}

export function profiles_tab_render(rootEl, api, options = {}) {
  if (!rootEl) throw new Error("profiles_tab_render: rootEl is required");
  const apiBase = options.apiBase || "/comfymodal";
  while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);

  let profiles = [];
  let selectedId = "";
  let selectedProfile = null;
  let selectedWorkflowApi = null;
  let selectedWorkflowUi = null;
  let slotCandidates = {};

  const root = el("div", { class: "testing-profiles-root" });
  const createStatus = el("div", { class: "testing-profiles-status" });
  const createName = el("input", {
    type: "text",
    placeholder: "Profile name (e.g. Flux2 Klein FP8)",
    class: "testing-profiles-name-input comfymodal-input",
  });
  const createBtn = el("button", {
    class: "comfymodal-primary-btn testing-profiles-create-btn",
    text: "Create from Canvas",
  });

  const listPane = el("div", { class: "testing-profiles-list", "data-testid": "profiles-list" });
  const editorPane = el("div", { class: "testing-profiles-editor", "data-testid": "profiles-editor" });

  async function loadProfiles() {
    const data = await fetchJson(`${apiBase}/comparison/profiles`);
    profiles = (data && data.profiles) || [];
    if (!selectedId && profiles.length) selectedId = profiles[0].id;
    if (selectedId && !profiles.some((p) => p.id === selectedId)) selectedId = profiles.length ? profiles[0].id : "";
    renderList();
    if (selectedId) await loadProfile(selectedId); else renderEditor();
  }

  async function loadProfile(profileId) {
    selectedId = profileId;
    try {
      const profileData = await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}`);
      selectedProfile = profileData.profile || null;
    } catch (e) {
      selectedProfile = null;
      renderList();
      renderEditor();
      return;
    }
    // Fetch workflow data — graceful if unavailable
    try {
      const workflowData = await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}/workflow`);
      selectedWorkflowApi = workflowData.workflow_api || null;
      selectedWorkflowUi = workflowData.workflow || null;
    } catch (wfError) {
      selectedWorkflowApi = null;
      selectedWorkflowUi = null;
    }
    slotCandidates = {};
    renderList();
    renderEditor();
  }

  function renderList() {
    while (listPane.firstChild) listPane.removeChild(listPane.firstChild);
    listPane.appendChild(el("div", { class: "testing-profiles-pane-title", text: "Saved Profiles" }));
    if (!profiles.length) {
      listPane.appendChild(el("div", { class: "testing-profiles-empty-state", text: "No profiles yet. Save the current workflow from canvas to create one." }));
      return;
    }
    const rows = el("div", { class: "testing-profiles-list-rows" });
    profiles.forEach((profile) => {
      const validation = profile.validation || {};
      const row = el("div", {
        class: `testing-profiles-row ${profile.id === selectedId ? "testing-profiles-row-active" : ""}`,
      }, [
        el("div", { class: "testing-profiles-row-header" }, [
          el("button", {
            class: "testing-profiles-row-name",
            text: profile.name || profile.id,
            onclick: () => loadProfile(profile.id),
          }),
          el("div", { class: "testing-profiles-row-badges", style: "display:flex;gap:4px;align-items:center" }, [
            normalizationBadge(profile),
            statusBadge(validation.status || "unknown"),
          ]),
        ]),
        el("div", { class: "testing-profiles-row-summary", text: modelStackSummary(profile.model_stack || {}) }),
        el("div", { class: "testing-profiles-row-actions" }, [
          el("button", { class: "comfymodal-secondary-btn", text: "Edit", onclick: () => loadProfile(profile.id) }),
          el("button", {
            class: "comfymodal-secondary-btn",
            text: "Validate",
            onclick: async () => {
              await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profile.id)}/validate`, { method: "POST" });
              await loadProfiles();
            },
          }),
          el("button", {
            class: "comfymodal-secondary-btn",
            text: "Duplicate",
            onclick: async () => {
              const nextName = window.prompt("Duplicate profile as:", `${profile.name || profile.id} (copy)`);
              if (!nextName || !nextName.trim()) return;
              await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profile.id)}/duplicate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: nextName.trim() }),
              });
              await loadProfiles();
            },
          }),
          el("button", {
            class: "comfymodal-destructive-btn",
            text: "Delete",
            onclick: async () => {
              if (!window.confirm(`Delete profile \"${profile.name || profile.id}\"?`)) return;
              await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profile.id)}`, { method: "DELETE" });
              if (selectedId === profile.id) selectedId = "";
              await loadProfiles();
            },
          }),
        ]),
      ]);
      rows.appendChild(row);
    });
    listPane.appendChild(rows);
  }

  function renderMappingSection(container) {
    const section = el("div", { class: "testing-profiles-mapping-section" }, [
      el("div", { class: "testing-profiles-section-title", text: "Mapping Assistant" }),
      el("div", { class: "testing-profiles-section-help", text: "Map prompt, seed, steps, guidance, resolution, and input image slots for this profile." }),
    ]);

    const detectRow = el("div", { class: "testing-profiles-inline-actions" }, [
      el("button", {
        class: "comfymodal-secondary-btn",
        text: "Auto-detect slots",
        onclick: async () => {
          const data = await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(selectedId)}/detect-slots`, { method: "POST" });
          slotCandidates = data.candidates || {};
          renderEditor();
        },
      }),
    ]);
    section.appendChild(detectRow);

    const form = el("div", { class: "testing-profiles-mapping-grid" });
    const currentSlots = clone((selectedProfile && selectedProfile.slots) || {});

    SLOT_KEYS.forEach((slotKey) => {
      const row = el("div", { class: "testing-profiles-mapping-row" });
      const enabled = !!(currentSlots[slotKey] && currentSlots[slotKey].node_id);
      const toggle = el("input", { type: "checkbox", checked: enabled });
      const select = el("select", { class: "comfymodal-input testing-profiles-slot-select" });
      select.appendChild(el("option", { value: "", text: `${slotKey} (unmapped)` }));
      const candidates = slotCandidates[slotKey] || [];
      candidates.forEach((candidate) => {
        const value = JSON.stringify({ node_id: candidate.node_id, path: candidate.path, field: candidate.field });
        const option = el("option", { value, text: `node ${candidate.node_id} - ${candidate.class_type}.${candidate.field}` });
        const cur = currentSlots[slotKey] || {};
        if (cur.node_id === candidate.node_id && cur.field === candidate.field && cur.path === candidate.path) option.selected = true;
        select.appendChild(option);
      });
      if (!candidates.length && currentSlots[slotKey] && currentSlots[slotKey].node_id) {
        select.appendChild(el("option", {
          value: JSON.stringify({ node_id: currentSlots[slotKey].node_id, path: currentSlots[slotKey].path, field: currentSlots[slotKey].field }),
          text: `node ${currentSlots[slotKey].node_id} - ${currentSlots[slotKey].field}`,
        }));
        select.value = JSON.stringify({ node_id: currentSlots[slotKey].node_id, path: currentSlots[slotKey].path, field: currentSlots[slotKey].field });
      }
      select.disabled = !toggle.checked;
      toggle.addEventListener("change", () => { select.disabled = !toggle.checked; });
      row.appendChild(el("label", { class: "testing-profiles-slot-label" }, [toggle, el("span", { text: slotKey })]));
      row.appendChild(select);
      form.appendChild(row);
    });

    section.appendChild(form);
    section.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      text: "Save Mappings",
      onclick: async () => {
        const nextSlots = {};
        form.querySelectorAll(".testing-profiles-mapping-row").forEach((row, index) => {
          const key = SLOT_KEYS[index];
          const checkbox = row.querySelector('input[type="checkbox"]');
          const select = row.querySelector("select");
          if (!checkbox.checked || !select.value) return;
          try {
            nextSlots[key] = JSON.parse(select.value);
          } catch {}
        });
        await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(selectedId)}/slots`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slots: nextSlots }),
        });
        await loadProfile(selectedId);
        await loadProfiles();
      },
    }));

    container.appendChild(section);
  }

  function renderModelEditor(container) {
    const loaderRows = extractLoaderRows(selectedWorkflowApi || {});
    const section = el("div", { class: "testing-profiles-model-section" }, [
      el("div", { class: "testing-profiles-section-title", text: "Model Triple / Loaders" }),
      el("div", { class: "testing-profiles-section-help", text: "Edit the saved workflow profile's checkpoint, UNet, CLIP, and VAE loader values here." }),
    ]);
    if (!loaderRows.length) {
      section.appendChild(el("div", { class: "testing-profiles-empty-state", text: "No editable loader nodes were found in this saved profile." }));
      container.appendChild(section);
      return;
    }

    const grid = el("div", { class: "testing-profiles-model-grid" });
    loaderRows.forEach((row) => {
      const input = el("input", {
        class: "comfymodal-input testing-profiles-model-input",
        type: "text",
        value: row.value,
        "data-node-id": row.nodeId,
        "data-field": row.field,
      });
      grid.appendChild(el("label", { class: "testing-profiles-field" }, [
        el("span", { class: "testing-profiles-field-label", text: row.label }),
        input,
      ]));
    });
    section.appendChild(grid);
    section.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      text: "Save model config",
      onclick: async () => {
        const nextWorkflowApi = clone(selectedWorkflowApi || {});
        grid.querySelectorAll(".testing-profiles-model-input").forEach((input) => {
          const nodeId = input.getAttribute("data-node-id");
          const field = input.getAttribute("data-field");
          if (nextWorkflowApi[nodeId] && nextWorkflowApi[nodeId].inputs) nextWorkflowApi[nodeId].inputs[field] = input.value;
        });
        await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(selectedId)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workflow_api: nextWorkflowApi, workflow: selectedWorkflowUi || undefined }),
        });
        await loadProfile(selectedId);
        await loadProfiles();
      },
    }));
    container.appendChild(section);
  }

  function renderEditor() {
    while (editorPane.firstChild) editorPane.removeChild(editorPane.firstChild);
    editorPane.appendChild(el("div", { class: "testing-profiles-pane-title", text: "Profile Editor" }));
    if (!selectedProfile) {
      editorPane.appendChild(el("div", { class: "testing-profiles-empty-state", text: "Select a saved profile to edit, validate, map, or update its model triple." }));
      return;
    }

    const validation = selectedProfile.validation || {};
    editorPane.appendChild(el("div", { class: "testing-profiles-editor-header", style: "display:flex;align-items:center;gap:8px;flex-wrap:wrap" }, [
      el("div", { class: "testing-profiles-editor-title", text: selectedProfile.name || selectedProfile.id }),
      normalizationBadge(selectedProfile),
      statusBadge(validation.status || "unknown"),
    ]));
    editorPane.appendChild(el("div", { class: "testing-profiles-editor-summary", text: modelStackSummary(selectedProfile.model_stack || {}) }));

    editorPane.appendChild(el("div", { class: "testing-profiles-inline-actions" }, [
      el("button", {
        class: "comfymodal-secondary-btn",
        text: "Rename",
        onclick: async () => {
          const nextName = window.prompt("Rename profile:", selectedProfile.name || selectedProfile.id);
          if (!nextName || !nextName.trim()) return;
          await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(selectedId)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: nextName.trim() }),
          });
          await loadProfiles();
          await loadProfile(selectedId);
        },
      }),
      el("button", {
        class: "comfymodal-secondary-btn",
        text: "Validate",
        onclick: async () => {
          await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(selectedId)}/validate`, { method: "POST" });
          await loadProfiles();
          await loadProfile(selectedId);
        },
      }),
    ]));

    if ((validation.warnings || []).length) {
      editorPane.appendChild(el("div", { class: "testing-profiles-warning-box", text: (validation.warnings || []).join("; ") }));
    }
    if ((validation.errors || []).length) {
      editorPane.appendChild(el("div", { class: "testing-profiles-error-box", text: (validation.errors || []).join("; ") }));
    }

    renderModelEditor(editorPane);
    renderMappingSection(editorPane);
  }

  createBtn.addEventListener("click", async () => {
    const name = createName.value.trim();
    if (!name) {
      createStatus.textContent = "Profile name is required.";
      return;
    }
    createBtn.disabled = true;
    createStatus.textContent = "Saving profile from canvas...";
    try {
      const graphData = await app.graphToPrompt();
      if (!graphData || !graphData.output) throw new Error("Could not export workflow as API JSON");
      const data = await fetchJson(`${apiBase}/comparison/profiles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, workflow_api: graphData.output, workflow: graphData.workflow || null }),
      });
      if (data && data.profile && data.profile.id) {
        await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(data.profile.id)}/detect-slots`, { method: "POST" });
        selectedId = data.profile.id;
      }
      createName.value = "";
      createStatus.textContent = "Profile saved.";
      await loadProfiles();
    } catch (e) {
      createStatus.textContent = e.message || String(e);
    }
    createBtn.disabled = false;
  });

  root.appendChild(el("div", { class: "testing-profiles-create-card" }, [
    el("div", { class: "testing-profiles-pane-title", text: "Create from Canvas" }),
    el("label", { class: "testing-profiles-field" }, [
      el("span", { class: "testing-profiles-field-label", text: "Profile name" }),
      createName,
    ]),
    el("div", { class: "testing-profiles-inline-actions" }, [createBtn]),
    createStatus,
  ]));

  root.appendChild(el("div", { class: "testing-profiles-workspace" }, [listPane, editorPane]));
  rootEl.appendChild(root);

  loadProfiles().catch((e) => {
    createStatus.textContent = e.message || String(e);
  });

  return { rootEl: root, stop() {} };
}
