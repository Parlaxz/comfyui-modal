// web/testing-setup.js
//
// Experiment Setup UI — Clean single-page editor.
//
// No phase rail. Sections are collapsible cards with clear hierarchy.
// Name/Notes are prominent. Workflows section has inline create/edit.
// Prompts are editable in-page with save-as-preset. Samplers use
// dropdowns with enable/disable toggles. Model triple config lives
// in a dedicated Model Profiles section.

import { app } from "../../scripts/app.js";

const SECTION_LABELS = {
  experiment: "Experiment",
  workflows: "Workflows & Models",
  modelProfiles: "Model Profiles",
  loras: "LoRAs",
  prompts: "Prompts",
  images: "Images",
  axes: "Axes",
  containers: "Execution",
  preview: "Review & Run",
};

const STEP_KEYS = [
  "experiment",
  "workflows",
  "modelProfiles",
  "loras",
  "prompts",
  "images",
  "axes",
  "containers",
  "preview",
];

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k === "html") e.innerHTML = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    } else if (k === "value") {
      e.value = props[k];
    } else if (k === "checked") {
      e.checked = !!props[k];
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

// ── Section card with collapse support ────────────────────────

function sectionCard(title, body, sectionKey, startCollapsed) {
  const collapsed = startCollapsed !== false;
  const card = el("div", {
    class: "testing-setup-section-card comfymodal-section-card testing-setup-section-collapsible",
    id: `testing-setup-section-${sectionKey}`,
    "data-section-key": sectionKey,
    "data-collapsed": collapsed ? "true" : "false",
  }, [
    el("div", {
      class: "comfymodal-section-card-header",
      style: "cursor:pointer;",
      onclick: function () {
        const current = card.getAttribute("data-collapsed");
        const next = current === "true" ? "false" : "true";
        card.setAttribute("data-collapsed", next);
      },
    }, [el("span", { text: title })]),
    el("div", { class: "comfymodal-section-card-body" }, body || []),
  ]);
  return card;
}

// ── Helpers ───────────────────────────────────────────────────

async function fetchJson(path, options = {}) {
  const res = await fetch(path, options);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!res.ok) {
    const msg = (data && data.message) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function status(text, level = "info") {
  return el("div", { class: `testing-setup-status testing-setup-status-${level}`, text });
}

function refreshable(target, builder) {
  return async () => {
    while (target.firstChild) target.removeChild(target.firstChild);
    target.appendChild(status("Loading\u2026"));
    try {
      const fresh = await builder();
      while (target.firstChild) target.removeChild(target.firstChild);
      fresh.forEach((n) => target.appendChild(n));
    } catch (e) {
      while (target.firstChild) target.removeChild(target.firstChild);
      target.appendChild(status("Error: " + (e.message || e), "error"));
    }
  };
}

// ── Step 1: Experiment (Name + Notes — large, prominent) ─────

function experimentSection(spec, onChange) {
  const nameInput = el("input", {
    type: "text",
    placeholder: "Give your experiment a name",
    value: (spec && spec.name) || "",
    class: "testing-setup-input comfymodal-input testing-setup-name-input",
  });
  nameInput.addEventListener("input", () => onChange({ ...(spec || {}), name: nameInput.value }));

  const notes = el("textarea", {
    placeholder: "Notes, hypothesis, observations\u2026",
    class: "testing-setup-textarea comfymodal-input testing-setup-notes-textarea",
  });
  notes.value = (spec && spec.notes) || "";
  notes.addEventListener("input", () => onChange({ ...(spec || {}), notes: notes.value }));

  return sectionCard(SECTION_LABELS.experiment, [
    el("div", { class: "testing-setup-experiment-fields" }, [
      el("label", { class: "testing-setup-field testing-setup-field-large" }, [
        el("span", { class: "testing-setup-field-label", text: "Name" }),
        nameInput,
      ]),
      el("label", { class: "testing-setup-field testing-setup-field-large" }, [
        el("span", { class: "testing-setup-field-label", text: "Notes" }),
        notes,
      ]),
    ]),
  ], "experiment", false);
}

// ── Step 2: Workflows & Models (inline create/edit/modify) ───

function workflowsSection(spec, onChange, apiBase) {
  const list = el("div", { class: "testing-setup-profiles" });
  const statusEl = el("div", { class: "testing-setup-section-status" });

  // ── Create from Canvas (primary action) ──
  const nameInput = el("input", {
    type: "text",
    placeholder: "Profile name (e.g. Flux2 Klein FP8)",
    class: "testing-setup-input comfymodal-input",
    style: "flex:1;",
  });

  const createBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Create from Canvas",
    title: "Save the current ComfyUI workflow as a comparison profile",
  });
  createBtn.addEventListener("click", async () => {
    const name = nameInput.value.trim();
    if (!name) {
      statusEl.textContent = "Enter a profile name first.";
      statusEl.className = "testing-setup-section-status testing-setup-status-error";
      return;
    }
    createBtn.disabled = true;
    statusEl.textContent = "Saving workflow\u2026";
    statusEl.className = "testing-setup-section-status testing-setup-status-info";
    try {
      const graphData = await app.graphToPrompt();
      if (!graphData || !graphData.output) {
        throw new Error("Could not export workflow as API JSON");
      }
      const data = await fetchJson(`${apiBase}/comparison/profiles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, workflow_api: graphData.output, workflow: graphData.workflow || null }),
      });
      if (data && data.profile && data.profile.id) {
        // Auto-detect slots
        try {
          await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(data.profile.id)}/detect-slots`, { method: "POST" });
        } catch (_) { /* non-fatal */ }
        statusEl.textContent = `Profile "${name}" saved.`;
        statusEl.className = "testing-setup-section-status testing-setup-status-ok";
        nameInput.value = "";
        onChange({ ...(spec || {}), _refresh: Date.now() });
        refresh();
      } else {
        statusEl.textContent = "Profile saved (no id returned).";
        statusEl.className = "testing-setup-section-status testing-setup-status-ok";
      }
    } catch (e) {
      statusEl.textContent = "Error: " + (e.message || e);
      statusEl.className = "testing-setup-section-status testing-setup-status-error";
    }
    createBtn.disabled = false;
  });

  nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") createBtn.click(); });

  // ── Profile list with inline edit/delete ──
  const refresh = refreshable(list, async () => {
    const data = await fetchJson(`${apiBase}/comparison/profiles`);
    const profiles = (data && data.profiles) || data || [];
    const out = [];
    if (profiles.length === 0) {
      out.push(el("div", { class: "testing-setup-empty-hint", text: "No profiles yet. Create one from the canvas above." }));
    }
    const sel = (spec && spec.workflows) || [];
    profiles.forEach((p) => {
      const profileId = p.id || p.profile_id || p.name;
      const isSelected = sel.some((s) => s.profile_id === profileId);
      const row = el("div", {
        class: `testing-setup-profile-row ${isSelected ? "testing-setup-profile-selected" : ""}`,
      }, [
        el("input", {
          type: "checkbox",
          class: "testing-setup-profile-checkbox",
          value: profileId,
          checked: isSelected,
          onchange: function () {
            const cur = (spec && spec.workflows) || [];
            const next = this.checked
              ? [...cur, { profile_id: profileId, loader_target_group_id: "g_default", main_triple: pickMainTriple(p), subprofile_triples: [], selected_triple_ids: ["main"], lora_slots: [] }]
              : cur.filter((s) => s.profile_id !== profileId);
            onChange({ ...(spec || {}), workflows: next });
          },
        }),
        el("div", { class: "testing-setup-profile-info" }, [
          el("span", { class: "testing-setup-profile-name", text: p.name || p.id }),
          el("span", { class: "testing-setup-profile-triple", text: tripleSummary(p) }),
        ]),
        el("div", { class: "testing-setup-profile-actions" }, [
          el("button", {
            class: "testing-setup-profile-action-btn comfymodal-secondary-btn",
            text: "Validate",
            title: "Validate this profile",
            onclick: async () => {
              statusEl.textContent = "Validating\u2026";
              try {
                const vdata = await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}/validate`, { method: "POST" });
                const validation = vdata.validation || {};
                statusEl.textContent = validation.status === "ready" ? "Profile is valid." : `Validation: ${validation.status || "unknown"}`;
                statusEl.className = "testing-setup-section-status " + (validation.status === "ready" ? "testing-setup-status-ok" : "testing-setup-status-warn");
              } catch (e) { statusEl.textContent = "Error: " + (e.message || e); statusEl.className = "testing-setup-section-status testing-setup-status-error"; }
            },
          }),
          el("button", {
            class: "testing-setup-profile-action-btn comfymodal-secondary-btn",
            text: "Duplicate",
            title: "Duplicate this profile",
            onclick: async () => {
              try {
                const ddata = await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}/duplicate`, { method: "POST" });
                statusEl.textContent = `Duplicated as ${(ddata.profile && ddata.profile.id) || "new profile"}.`;
                onChange({ ...(spec || {}), _refresh: Date.now() });
                refresh();
              } catch (e) { statusEl.textContent = "Error: " + (e.message || e); }
            },
          }),
          el("button", {
            class: "testing-setup-profile-action-btn comfymodal-destructive-btn",
            text: "Delete",
            title: "Delete this profile",
            onclick: async () => {
              if (!window.confirm(`Delete profile "${p.name || profileId}"?`)) return;
              try {
                await fetchJson(`${apiBase}/comparison/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
                statusEl.textContent = "Deleted.";
                onChange({ ...(spec || {}), workflows: ((spec && spec.workflows) || []).filter((s) => s.profile_id !== profileId), _refresh: Date.now() });
                refresh();
              } catch (e) { statusEl.textContent = "Error: " + (e.message || e); }
            },
          }),
        ]),
      ]);
      out.push(row);
    });
    return out;
  });

  refresh();

  return sectionCard(SECTION_LABELS.workflows, [
    el("div", { class: "testing-setup-create-row" }, [
      nameInput,
      createBtn,
    ]),
    statusEl,
    list,
  ], "workflows", false);
}

// ── Model Profiles section (model triple configuration) ───────

function modelProfilesSection(spec, onChange, apiBase) {
  const workflows = (spec && spec.workflows) || [];
  const body = el("div", { class: "testing-setup-model-profiles" });

  function rebuild() {
    while (body.firstChild) body.removeChild(body.firstChild);
    if (workflows.length === 0) {
      body.appendChild(el("div", { class: "testing-setup-empty-hint", text: "Select a workflow above to configure its model triple." }));
      return;
    }
    workflows.forEach((wf, idx) => {
      const triple = wf.main_triple || {};
      const unetInput = el("input", {
        type: "text",
        placeholder: "unet model",
        class: "testing-setup-input comfymodal-input",
        value: triple.unet || "",
      });
      unetInput.addEventListener("input", () => {
        const next = [...workflows];
        next[idx] = { ...next[idx], main_triple: { ...(next[idx].main_triple || {}), unet: unetInput.value } };
        onChange({ ...(spec || {}), workflows: next });
      });
      const clipInput = el("input", {
        type: "text",
        placeholder: "clip model",
        class: "testing-setup-input comfymodal-input",
        value: triple.clip || "",
      });
      clipInput.addEventListener("input", () => {
        const next = [...workflows];
        next[idx] = { ...next[idx], main_triple: { ...(next[idx].main_triple || {}), clip: clipInput.value } };
        onChange({ ...(spec || {}), workflows: next });
      });
      const vaeInput = el("input", {
        type: "text",
        placeholder: "vae model",
        class: "testing-setup-input comfymodal-input",
        value: triple.vae || "",
      });
      vaeInput.addEventListener("input", () => {
        const next = [...workflows];
        next[idx] = { ...next[idx], main_triple: { ...(next[idx].main_triple || {}), vae: vaeInput.value } };
        onChange({ ...(spec || {}), workflows: next });
      });

      body.appendChild(el("div", { class: "testing-setup-model-profile-entry" }, [
        el("div", { class: "testing-setup-model-profile-name", text: wf.profile_id }),
        el("div", { class: "testing-setup-field-grid" }, [
          el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "UNet" }), unetInput]),
          el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "CLIP" }), clipInput]),
          el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "VAE" }), vaeInput]),
        ]),
      ]));
    });
  }
  rebuild();

  return sectionCard(SECTION_LABELS.modelProfiles, [body], "modelProfiles", true);
}

function pickMainTriple(profile) {
  const rawSlots = (profile && profile.slots) || {};
  const main = { id: "main" };
  if (typeof rawSlots === "object" && !Array.isArray(rawSlots)) {
    const findVal = (cat) => { const key = Object.keys(rawSlots).find((k) => k.toLowerCase().includes(cat)); return key ? rawSlots[key] : null; };
    const unet = findVal("unet"); const clip = findVal("clip"); const vae = findVal("vae");
    if (unet && unet.value) main.unet = unet.value;
    if (clip && clip.value) main.clip = clip.value;
    if (vae && vae.value) main.vae = vae.value;
  } else if (Array.isArray(rawSlots)) {
    const find = (cat) => rawSlots.find((s) => (s.category || s.key || "").toLowerCase().includes(cat));
    const unet = find("unet"); const clip = find("clip"); const vae = find("vae");
    if (unet && unet.value) main.unet = unet.value;
    if (clip && clip.value) main.clip = clip.value;
    if (vae && vae.value) main.vae = vae.value;
  }
  return main;
}

function tripleSummary(profile) {
  const t = pickMainTriple(profile);
  return [t.unet, t.clip, t.vae].filter(Boolean).join(" / ") || "(no model triple)";
}

// ── Step 3: LoRAs ─────────────────────────────────────────────

function makeLoraEntryRow(entry, idx, onEntryChange) {
  const item = (entry.loras && entry.loras[idx]) || {};
  const fileInput = el("input", {
    type: "text", placeholder: "lora.safetensors",
    class: "testing-setup-input comfymodal-input testing-setup-lora-entry-file",
    value: item.file || "",
  });
  fileInput.addEventListener("input", () => {
    const updatedLoras = [...(entry.loras || [])];
    updatedLoras[idx] = { ...(updatedLoras[idx] || {}), file: fileInput.value };
    onEntryChange({ ...entry, loras: updatedLoras });
  });
  const modelStrength = el("input", {
    type: "text", placeholder: "model strengths (csv)",
    class: "testing-setup-input comfymodal-input testing-setup-lora-entry-ms",
    value: item.model_strength ? item.model_strength.join(",") : "0.7",
  });
  modelStrength.addEventListener("input", () => {
    const vals = modelStrength.value.split(",").map((s) => parseFloat(s.trim())).filter((n) => !Number.isNaN(n));
    const updatedLoras = [...(entry.loras || [])];
    updatedLoras[idx] = { ...(updatedLoras[idx] || {}), model_strength: vals.length ? vals : [0.7] };
    onEntryChange({ ...entry, loras: updatedLoras });
  });
  const clipStrength = el("input", {
    type: "text", placeholder: "clip strengths (csv)",
    class: "testing-setup-input comfymodal-input testing-setup-lora-entry-cs",
    value: item.clip_strength ? item.clip_strength.join(",") : "0.7",
  });
  clipStrength.addEventListener("input", () => {
    const vals = clipStrength.value.split(",").map((s) => parseFloat(s.trim())).filter((n) => !Number.isNaN(n));
    const updatedLoras = [...(entry.loras || [])];
    updatedLoras[idx] = { ...(updatedLoras[idx] || {}), clip_strength: vals.length ? vals : [0.7] };
    onEntryChange({ ...entry, loras: updatedLoras });
  });
  const removeBtn = el("button", {
    class: "testing-setup-lora-entry-remove comfymodal-destructive-btn",
    text: "\u00d7",
    style: "padding:4px 8px;font-size:14px;",
  });
  removeBtn.addEventListener("click", () => {
    const updatedLoras = [...(entry.loras || [])];
    updatedLoras.splice(idx, 1);
    onEntryChange({ ...entry, loras: updatedLoras.length ? updatedLoras : [{ file: "", model_strength: [0.7], clip_strength: [0.7], enabled: true }] });
  });
  return el("div", { class: "testing-setup-lora-entry-row" }, [
    el("label", { class: "testing-setup-lora-entry-field" }, [el("span", { text: "File" }), fileInput]),
    el("label", { class: "testing-setup-lora-entry-field" }, [el("span", { text: "Model" }), modelStrength]),
    el("label", { class: "testing-setup-lora-entry-field" }, [el("span", { text: "CLIP" }), clipStrength]),
    removeBtn,
  ]);
}

function makeLoraRow(entry, onEntryChange) {
  const cb = el("input", { type: "checkbox", checked: entry.enabled !== false });
  cb.addEventListener("change", () => onEntryChange({ ...entry, enabled: cb.checked }));
  const labelEl = el("span", { class: "testing-setup-lora-name", text: entry.label || entry.id });
  const entriesContainer = el("div", { class: "testing-setup-lora-entries" });
  function rebuildEntries() {
    while (entriesContainer.firstChild) entriesContainer.removeChild(entriesContainer.firstChild);
    (entry.loras || []).forEach((_, idx) => { entriesContainer.appendChild(makeLoraEntryRow(entry, idx, onEntryChange)); });
    const addEntryBtn = el("button", { class: "testing-setup-btn testing-setup-lora-add-entry comfymodal-secondary-btn", text: "+ Add LoRA entry" });
    addEntryBtn.addEventListener("click", () => { const updatedLoras = [...(entry.loras || [])]; updatedLoras.push({ file: "", model_strength: [0.7], clip_strength: [0.7], enabled: true }); onEntryChange({ ...entry, loras: updatedLoras }); });
    entriesContainer.appendChild(addEntryBtn);
  }
  rebuildEntries();
  return el("div", { class: "testing-setup-lora-row" }, [
    el("div", { class: "testing-setup-lora-header" }, [cb, labelEl]),
    entriesContainer,
  ]);
}

function lorasSection(spec, onChange) {
  const selections = (spec && spec.loras && spec.loras.selections) || [];
  const list = el("div", { class: "testing-setup-loras" });
  function getSelections() { return (spec && spec.loras && spec.loras.selections) || []; }
  function updateSelections(next) { onChange({ ...(spec || {}), loras: { selections: next } }); }
  const rebuild = () => {
    while (list.firstChild) list.removeChild(list.firstChild);
    const current = getSelections();
    const visible = current.filter((s) => s.id !== "L_no" || current.length === 1);
    visible.forEach((entry) => {
      list.appendChild(makeLoraRow(entry, (updated) => {
        const cur = getSelections();
        const idx = cur.findIndex((l) => l.id === entry.id);
        if (idx >= 0) { const next = [...cur]; next[idx] = updated; updateSelections(next); }
      }));
    });
    const addBtn = el("button", { class: "testing-setup-btn testing-setup-add-lora comfymodal-primary-btn", text: "+ Add LoRA" });
    addBtn.addEventListener("click", () => {
      const cur = getSelections();
      const newId = `L_${Date.now().toString(36)}`;
      updateSelections([...cur, { id: newId, label: `LoRA ${cur.length}`, loras: [{ file: "", model_strength: [0.7], clip_strength: [0.7], enabled: true }], enabled: true }]);
    });
    list.appendChild(addBtn);
  };
  rebuild();
  return sectionCard(SECTION_LABELS.loras, [list], "loras", true);
}

// ── Step 4: Prompts (editable in-page + save-as-preset) ──────

function promptsSection(spec, onChange, apiBase) {
  const promptText = ((spec && spec.prompts && spec.prompts.items && spec.prompts.items[0] && spec.prompts.items[0].text) || "");
  const negativeText = ((spec && spec.prompts && spec.prompts.items && spec.prompts.items[0] && spec.prompts.items[0].negative) || "");

  const positiveArea = el("textarea", {
    class: "testing-setup-textarea comfymodal-input testing-setup-prompt-textarea",
    placeholder: "Positive prompt\u2026",
  });
  positiveArea.value = promptText;
  positiveArea.addEventListener("input", () => {
    const items = [{ text: positiveArea.value, negative: negativeArea.value }];
    onChange({ ...(spec || {}), prompts: { items, preset_id: (spec && spec.prompts && spec.prompts.preset_id) || "" } });
  });

  const negativeArea = el("textarea", {
    class: "testing-setup-textarea comfymodal-input testing-setup-prompt-textarea",
    placeholder: "Negative prompt (optional)\u2026",
  });
  negativeArea.value = negativeText;
  negativeArea.addEventListener("input", () => {
    const items = [{ text: positiveArea.value, negative: negativeArea.value }];
    onChange({ ...(spec || {}), prompts: { items, preset_id: (spec && spec.prompts && spec.prompts.preset_id) || "" } });
  });

  // Preset dropdown
  const presetDropdown = el("select", { class: "testing-setup-select comfymodal-input testing-setup-preset-dropdown" });
  presetDropdown.appendChild(el("option", { value: "", text: "Load a preset\u2026" }));

  // Save as preset button
  const savePresetBtn = el("button", {
    class: "comfymodal-secondary-btn testing-setup-save-preset-btn",
    text: "Save as Preset",
  });

  const presetStatus = el("div", { class: "testing-setup-section-status" });

  // Load presets into dropdown
  async function loadPresets() {
    try {
      const data = await fetchJson(`${apiBase}/presets/prompts`);
      const presets = (data && data.presets) || [];
      // Clear existing options except the placeholder
      while (presetDropdown.options.length > 1) presetDropdown.remove(1);
      presets.forEach((p) => {
        const opt = el("option", { value: p.id });
        const dateStr = p.created_at ? new Date(p.created_at).toLocaleDateString() : "";
        opt.textContent = p.name || p.id;
        if (dateStr) opt.textContent += `  (${dateStr})`;
        presetDropdown.appendChild(opt);
      });
    } catch (_) { /* non-fatal */ }
  }
  loadPresets();

  // Load preset on selection
  presetDropdown.addEventListener("change", async () => {
    const presetId = presetDropdown.value;
    if (!presetId) return;
    try {
      const data = await fetchJson(`${apiBase}/presets/prompts`);
      const presets = (data && data.presets) || [];
      const preset = presets.find((p) => p.id === presetId);
      if (preset && preset.items && preset.items.length > 0) {
        positiveArea.value = preset.items[0].text || "";
        negativeArea.value = preset.items[0].negative || "";
        const items = [{ text: positiveArea.value, negative: negativeArea.value }];
        onChange({ ...(spec || {}), prompts: { items, preset_id: presetId }, prompt_preset_id: presetId });
      }
    } catch (e) {
      presetStatus.textContent = "Error loading preset: " + (e.message || e);
    }
    presetDropdown.value = "";
  });

  // Save as preset
  savePresetBtn.addEventListener("click", async () => {
    const name = window.prompt("Save prompt as preset\u2026\nName:", "");
    if (!name || !name.trim()) return;
    savePresetBtn.disabled = true;
    try {
      const items = [{ text: positiveArea.value, negative: negativeArea.value }];
      await fetchJson(`${apiBase}/presets/prompts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), items }),
      });
      presetStatus.textContent = `Preset "${name.trim()}" saved.`;
      presetStatus.className = "testing-setup-section-status testing-setup-status-ok";
      await loadPresets();
    } catch (e) {
      presetStatus.textContent = "Error: " + (e.message || e);
      presetStatus.className = "testing-setup-section-status testing-setup-status-error";
    }
    savePresetBtn.disabled = false;
    setTimeout(() => { presetStatus.textContent = ""; }, 3000);
  });

  return sectionCard(SECTION_LABELS.prompts, [
    el("div", { class: "testing-setup-prompt-editor" }, [
      el("label", { class: "testing-setup-field testing-setup-field-large" }, [
        el("span", { class: "testing-setup-field-label", text: "Positive" }),
        positiveArea,
      ]),
      el("label", { class: "testing-setup-field testing-setup-field-large" }, [
        el("span", { class: "testing-setup-field-label", text: "Negative" }),
        negativeArea,
      ]),
    ]),
    el("div", { class: "testing-setup-preset-bar" }, [
      presetDropdown,
      savePresetBtn,
    ]),
    presetStatus,
  ], "prompts", false);
}

// ── Step 5: Images ────────────────────────────────────────────

function imagesSection(spec, onChange, apiBase) {
  const list = el("div", { class: "testing-setup-images" });
  const refresh = refreshable(list, async () => {
    const data = await fetchJson(`${apiBase}/presets/images`);
    const presets = (data && data.presets) || [];
    const out = [];
    out.push(el("div", { class: "testing-setup-section-help", text: "Pick an image preset (optional):" }));
    if (presets.length === 0) {
      out.push(status("No image presets. Create one in Settings.", "warn"));
    }
    const sel = (spec && spec.image_preset_id) || "";
    presets.forEach((p) => {
      const cb = el("input", { type: "radio", name: "image-preset", value: p.id });
      cb.checked = sel === p.id;
      cb.addEventListener("change", () => { onChange({ ...(spec || {}), image_preset_id: p.id, images: { mode: "cartesian", items: (p.items || []).map((i) => i.content_hash || i.id) } }); });
      out.push(el("label", { class: "testing-setup-preset-row" }, [cb, el("span", { text: p.name || p.id })]));
    });
    return out;
  });
  refresh();
  return sectionCard(SECTION_LABELS.images, [list], "images", true);
}

// ── Step 6: Axes (samplers dropdown + enable/disable + advanced toggle) ──

const SAMPLER_OPTIONS = [
  "euler", "euler_ancestral", "heun", "heunpp2", "dpm_2", "dpm_2_ancestral",
  "lms", "dpm_fast", "dpm_adaptive", "dpmpp_2s_ancestral", "dpmpp_sde",
  "dpmpp_sde_gpu", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_2m_sde_gpu",
  "dpmpp_3m_sde", "dpmpp_3m_sde_gpu", "ddpm", "lcm", "ddim", "uni_pc",
  "uni_pc_bh2",
];

const SCHEDULER_OPTIONS = [
  "normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform", "beta",
];

// Default disabled samplers (most should be disabled)
const DEFAULT_ENABLED_SAMPLERS = ["euler", "euler_ancestral", "dpmpp_2m"];

function axesSection(spec, onChange) {
  const axes = (spec && spec.axes) || { shared: { seed: { mode: "list", values: [1, 2, 3] } }, per_workflow: {} };

  // Seeds
  const seedInput = el("input", {
    type: "text", placeholder: "1,2,3,4,5",
    class: "testing-setup-input comfymodal-input",
    value: (axes.shared && axes.shared.seed && axes.shared.seed.values) ? axes.shared.seed.values.join(",") : "1,2,3",
  });
  seedInput.addEventListener("input", () => {
    const vals = seedInput.value.split(",").map((s) => parseInt(s.trim(), 10)).filter((n) => !Number.isNaN(n));
    onChange({ ...(spec || {}), axes: { ...(axes || {}), shared: { ...(axes.shared || {}), seed: { mode: "list", values: vals } } } });
  });

  // Sampler dropdown with enable/disable
  const samplerContainer = el("div", { class: "testing-setup-sampler-grid" });
  const enabledSamplers = (axes.shared && axes.shared.sampler && axes.shared.sampler.values) || DEFAULT_ENABLED_SAMPLERS;

  function rebuildSamplers() {
    while (samplerContainer.firstChild) samplerContainer.removeChild(samplerContainer.firstChild);
    SAMPLER_OPTIONS.forEach((sampler) => {
      const isEnabled = enabledSamplers.includes(sampler);
      const cb = el("input", {
        type: "checkbox",
        class: "testing-setup-sampler-toggle",
        checked: isEnabled,
      });
      cb.addEventListener("change", () => {
        const current = (axes.shared && axes.shared.sampler && axes.shared.sampler.values) || [...DEFAULT_ENABLED_SAMPLERS];
        const next = cb.checked
          ? [...current, sampler]
          : current.filter((s) => s !== sampler);
        onChange({ ...(spec || {}), axes: { ...axes, shared: { ...(axes.shared || {}), sampler: { mode: "list", values: next } } } });
      });
      const row = el("label", { class: `testing-setup-sampler-row ${isEnabled ? "testing-setup-sampler-enabled" : "testing-setup-sampler-disabled"}` }, [
        cb,
        el("span", { class: "testing-setup-sampler-name", text: sampler }),
      ]);
      samplerContainer.appendChild(row);
    });
  }
  rebuildSamplers();

  // Advanced fields
  const stepsInput = el("input", { type: "text", placeholder: "20,30", class: "testing-setup-input comfymodal-input", value: "20" });
  stepsInput.addEventListener("input", () => {
    const vals = stepsInput.value.split(",").map((s) => parseInt(s.trim(), 10)).filter((n) => !Number.isNaN(n));
    onChange({ ...(spec || {}), axes: { ...(axes || {}), per_workflow: { ...(axes.per_workflow || {}), p1: { ...((axes.per_workflow || {}).p1 || {}), steps: { mode: "list", values: vals } } } } });
  });
  const guidanceInput = el("input", { type: "text", placeholder: "3.5,7.5", class: "testing-setup-input comfymodal-input", value: "3.5" });
  guidanceInput.addEventListener("input", () => {
    const vals = guidanceInput.value.split(",").map((s) => parseFloat(s.trim())).filter((n) => !Number.isNaN(n));
    onChange({ ...(spec || {}), axes: { ...(axes || {}), shared: { ...(axes.shared || {}), guidance: { mode: "list", values: vals } } } });
  });

  // Scheduler dropdown
  const schedulerSelect = el("select", { class: "testing-setup-select comfymodal-input" });
  SCHEDULER_OPTIONS.forEach((s) => {
    schedulerSelect.appendChild(el("option", { value: s, text: s }));
  });
  schedulerSelect.value = (axes.shared && axes.shared.scheduler && axes.shared.scheduler.value) || "normal";
  schedulerSelect.addEventListener("change", () => onChange({ ...(spec || {}), axes: { ...axes, shared: { ...(axes.shared || {}), scheduler: { mode: "single", value: schedulerSelect.value } } } }));

  const denoiseInput = el("input", { type: "text", value: "1.0", class: "testing-setup-input comfymodal-input" });
  denoiseInput.addEventListener("input", () => onChange({ ...(spec || {}), axes: { ...axes, shared: { ...(axes.shared || {}), denoise: { mode: "single", value: parseFloat(denoiseInput.value) || 1.0 } } } }));

  // Essential fields
  const essentialGrid = el("div", { class: "testing-setup-field-grid" }, [
    el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "Seeds" }), seedInput]),
  ]);

  // Sampler section
  const samplerSection = el("div", { class: "testing-setup-sampler-section" }, [
    el("div", { class: "testing-setup-sampler-header" }, [
      el("span", { class: "testing-setup-field-label", text: "Samplers" }),
      el("span", { class: "testing-setup-sampler-hint", text: "Enable the samplers to sweep" }),
    ]),
    samplerContainer,
  ]);

  // Advanced fields
  const advancedBody = el("div", { class: "advanced-body" }, [
    el("div", { class: "testing-setup-field-grid" }, [
      el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "Steps" }), stepsInput]),
      el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "Guidance" }), guidanceInput]),
      el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "Scheduler" }), schedulerSelect]),
      el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "Denoise" }), denoiseInput]),
    ]),
  ]);

  const advancedToggle = el("details", { class: "testing-setup-advanced-toggle" }, [
    el("summary", { text: "Advanced axes" }),
    advancedBody,
  ]);

  return sectionCard(SECTION_LABELS.axes, [essentialGrid, samplerSection, advancedToggle], "axes", false);
}

// ── Step 7: Execution ─────────────────────────────────────────

function containersSection(spec, onChange) {
  const mode = el("select", { class: "testing-setup-select comfymodal-input" }, [
    el("option", { value: "single", text: "Single container" }),
    el("option", { value: "multi", text: "Multi-container" }),
  ]);
  mode.value = (spec && spec.container_mode) || "single";
  const max = el("input", { type: "number", min: "1", max: "8", value: String((spec && spec.max_containers) || 1), class: "testing-setup-input comfymodal-input" });
  mode.addEventListener("change", () => onChange({ ...(spec || {}), container_mode: mode.value }));
  max.addEventListener("input", () => onChange({ ...(spec || {}), max_containers: parseInt(max.value, 10) || 1 }));
  return sectionCard(SECTION_LABELS.containers, [
    el("div", { class: "testing-setup-field-grid" }, [
      el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "Mode" }), mode]),
      el("label", { class: "testing-setup-field" }, [el("span", { class: "testing-setup-field-label", text: "Max containers" }), max]),
    ]),
  ], "containers", true);
}

// ── Validation ────────────────────────────────────────────────

function validateSpec(spec) {
  const errors = [];
  const selections = (spec && spec.loras && spec.loras.selections) || [];
  for (const sel of selections) {
    if (sel.id === "L_no") continue;
    if (sel.enabled === false) continue;
    for (const l of sel.loras || []) {
      if (l.enabled === false) continue;
      if (!l.file || !l.file.trim()) { errors.push(`LoRA "${sel.label}": file path is required`); }
      if (l.model_strength && !l.model_strength.every((v) => typeof v === "number" && !Number.isNaN(v))) { errors.push(`LoRA "${sel.label}": invalid model_strength values`); }
      if (l.clip_strength && !l.clip_strength.every((v) => typeof v === "number" && !Number.isNaN(v))) { errors.push(`LoRA "${sel.label}": invalid clip_strength values`); }
    }
  }
  if (!spec.workflows || spec.workflows.length === 0) { errors.push("Select at least one workflow profile"); }
  return errors;
}

// ── Step 8: Review & Run ──────────────────────────────────────

function previewSection(spec, onRun, onCompile, apiBase) {
  const out = el("div", { class: "testing-setup-preview" });
  const compileBtn = el("button", { class: "comfymodal-primary-btn testing-setup-compile-btn", text: "Compile" });
  compileBtn.addEventListener("click", async () => {
    while (out.firstChild) out.removeChild(out.firstChild);
    const errs = validateSpec(spec);
    if (errs.length > 0) { errs.forEach((e) => out.appendChild(status(e, "error"))); return; }
    out.appendChild(status("Compiling\u2026"));
    try {
      const data = await onCompile();
      while (out.firstChild) out.removeChild(out.firstChild);
      const cellCount = (data.compilation && data.compilation.cells) ? data.compilation.cells.length : 0;
      const ckCount = (data.compilation && data.compilation.checkpoints) ? data.compilation.checkpoints.length : 0;
      out.appendChild(status(`Compiled: ${ckCount} checkpoints, ${cellCount} cells.`, "ok"));
      const runBtn = el("button", { class: "comfymodal-primary-btn testing-setup-run", text: "Run" });
      runBtn.addEventListener("click", async () => {
        runBtn.disabled = true;
        try {
          await onRun();
          out.appendChild(status("Run started. See Results tab.", "ok"));
        } catch (e) { out.appendChild(status("Run failed: " + (e.message || e), "error")); runBtn.disabled = false; }
      });
      out.appendChild(runBtn);
    } catch (e) {
      while (out.firstChild) out.removeChild(out.firstChild);
      out.appendChild(status("Compile failed: " + (e.message || e), "error"));
    }
  });
  return sectionCard(SECTION_LABELS.preview, [
    el("div", { class: "testing-setup-finish-zone testing-setup-finish-zone-prominent" }, [out, compileBtn]),
  ], "preview", false);
}

// ── Public mount function ──────────────────────────────────────

export function setup_tab_render(rootEl, api, options = {}) {
  if (!rootEl) throw new Error("setup_tab_render: rootEl is required");
  const apiBase = options.apiBase || "/comfymodal";
  const onDraftChange = options.onDraftChange || (() => {});
  const onRun = options.onRun || (() => {});

  let spec = options.draft || options.experiment || defaultSpec();

  while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);

  const shell = el("div", { class: "testing-setup-root" });

  const handler = (next) => {
    spec = mergeSpec(spec, next);
    onDraftChange(spec);
  };

  const sectionsContainer = el("div", { class: "testing-setup-sections" });

  // Build section cards — no rail, just clean stacked sections
  const sectionBuilders = [
    { key: "experiment", fn: () => experimentSection(spec, handler) },
    { key: "workflows", fn: () => workflowsSection(spec, handler, apiBase) },
    { key: "modelProfiles", fn: () => modelProfilesSection(spec, handler, apiBase) },
    { key: "loras", fn: () => lorasSection(spec, handler) },
    { key: "prompts", fn: () => promptsSection(spec, handler, apiBase) },
    { key: "images", fn: () => imagesSection(spec, handler, apiBase) },
    { key: "axes", fn: () => axesSection(spec, handler) },
    { key: "containers", fn: () => containersSection(spec, handler) },
    { key: "preview", fn: () => previewSection(spec,
      async () => { const result = await doRun(spec, apiBase); const expId = result && result.experiment_id ? result.experiment_id : null; onDraftChange(spec); onRun(expId); return { compilation: spec }; },
      () => doCompile(spec, apiBase), apiBase,
    )},
  ];

  sectionBuilders.forEach(({ fn }) => { sectionsContainer.appendChild(fn()); });
  shell.appendChild(sectionsContainer);
  rootEl.appendChild(shell);

  return {
    getSpec: () => spec,
    rootEl: shell,
    destroy() {},
  };
}

function defaultSpec() {
  return {
    name: "Untitled experiment",
    notes: "",
    workflows: [],
    prompts: { items: [] },
    images: { mode: "cartesian", items: [] },
    loras: { selections: [{ id: "L_no", label: "No LoRA", loras: [], enabled: true }] },
    axes: { shared: { seed: { mode: "list", values: [1, 2, 3] } }, per_workflow: {} },
    container_mode: "single",
    max_containers: 1,
  };
}

function mergeSpec(prev, next) { return { ...prev, ...next }; }

async function doCompile(spec, apiBase) {
  const payload = { spec: { experiment_id: makeExpId(spec), name: spec.name || "Untitled", notes: spec.notes || "", workflows: spec.workflows || [], prompts: spec.prompts || { items: [] }, images: spec.images || { mode: "cartesian", items: [] }, loras: spec.loras || { selections: [] }, axes: spec.axes || { shared: {}, per_workflow: {} } } };
  return await fetchJson(`${apiBase}/experiments/compile`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

async function doRun(spec, apiBase) {
  const expId = makeExpId(spec);
  const payload = { spec: { experiment_id: expId, name: spec.name || "Untitled", notes: spec.notes || "", workflows: spec.workflows || [], prompts: spec.prompts || { items: [] }, images: spec.images || { mode: "cartesian", items: [] }, loras: spec.loras || { selections: [] }, axes: spec.axes || { shared: {}, per_workflow: {} } }, max_containers: spec.max_containers || 1 };
  const created = await fetchJson(`${apiBase}/experiments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const startResult = await fetchJson(`${apiBase}/experiments/${encodeURIComponent(expId)}/start`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (startResult && (startResult.error || startResult.status === "error")) { throw new Error((startResult.message || startResult.error || "Start returned an error") + " \u2014 experiment was created but not started"); }
  return created;
}

function makeExpId(spec) {
  const slug = (spec.name || "exp").toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40);
  return `${slug}-${Date.now().toString(36)}`;
}

export const _internal = { SECTION_LABELS, el, section: (t, b) => el("section", { class: "testing-setup-section" }, [el("h3", { class: "testing-setup-section-title", text: t }), el("div", { class: "testing-setup-section-body" }, b || [])]), defaultSpec };
