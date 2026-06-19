import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const MODAL_PREFIX = "/comfymodal";

// ─── Storage Keys ─────────────────────────────────────────────────────────
const STORAGE_PROFILES_TAB = "comfymodal_comparison_profiles_tab";
const STORAGE_RUNNER_INPUTS = "comfymodal_comparison_runner_inputs";
const STORAGE_RUNNER_CONFIG = "comfymodal_comparison_runner_config";
const STORAGE_SELECTED_PROFILES = "comfymodal_comparison_selected_profiles";

// ─── Style Helpers (matching modal-settings.js) ───────────────────────────
function _btnStyle(variant) {
  if (variant === "primary") {
    return "background: #3a6fcc; border: 1px solid #4a7fe0; color: #fff; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; width: 100%; font-weight: 600; box-sizing: border-box;";
  }
  if (variant === "danger") {
    return "background: #c53030; border: 1px solid #e05050; color: #fff; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; width: 100%; font-weight: 600; box-sizing: border-box;";
  }
  return "background: #3a3a3a; border: 1px solid #555; color: #ddd; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; box-sizing: border-box;";
}

function _inputStyle() {
  return "background: #222; border: 1px solid #444; color: #ddd; padding: 5px 8px; border-radius: 4px; font-size: 12px; width: 100%; box-sizing: border-box; outline: none;";
}

function _segmentBtnStyle(active) {
  if (active) {
    return "flex: 1; padding: 7px 0; border: none; cursor: pointer; font-size: 12px; font-weight: 600; background: #3a6fcc; color: #fff; transition: background 0.2s;";
  }
  return "flex: 1; padding: 7px 0; border: none; cursor: pointer; font-size: 12px; background: #2a2a2a; color: #888; transition: background 0.2s;";
}

function _showToast(message, type) {
  const toast = document.createElement("div");
  toast.setAttribute("role", "alert");
  toast.setAttribute("aria-live", "polite");
  const bgMap = { success: "#1a3a1a", error: "#3d1010", info: "#1a2a3a" };
  const colorMap = { success: "#7ed321", error: "#e05050", info: "#6a9fd8" };
  toast.style.cssText = "position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: " + (bgMap[type] || bgMap.info) + "; color: " + (colorMap[type] || colorMap.info) + "; padding: 8px 16px; border-radius: 6px; font-size: 12px; z-index: 10000; pointer-events: none; opacity: 1; transition: opacity 0.5s ease; border: 1px solid " + (colorMap[type] || colorMap.info) + ";";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = "0"; }, 1500);
  setTimeout(() => { toast.remove(); }, 2100);
}

function _showConfirmDialog(message) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.style.cssText = "position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 99999; display: flex; align-items: center; justify-content: center;";
    const box = document.createElement("div");
    box.style.cssText = "background: #1e1e2e; border: 1px solid #444; border-radius: 8px; padding: 24px; max-width: 420px; width: 90%;";
    const msgEl = document.createElement("div");
    msgEl.style.cssText = "color: #ddd; font-size: 14px; margin-bottom: 20px; line-height: 1.5;";
    msgEl.textContent = message;
    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display: flex; gap: 8px; justify-content: flex-end;";
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = "background: transparent; border: 1px solid #555; color: #aaa; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px;";
    const confirmBtn = document.createElement("button");
    confirmBtn.textContent = "Confirm";
    confirmBtn.style.cssText = "background: #c53030; border: none; color: #fff; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px;";
    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(confirmBtn);
    box.appendChild(msgEl);
    box.appendChild(btnRow);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    function close(result) { overlay.remove(); document.removeEventListener("keydown", escHandler); resolve(result); }
    const escHandler = (e) => { if (e.key === "Escape") close(false); };
    document.addEventListener("keydown", escHandler);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(false); });
    cancelBtn.onclick = () => close(false);
    confirmBtn.onclick = () => close(true);
  });
}

function _createCollapsibleSection(title, opts) {
  const { defaultOpen, badge } = opts || {};
  const wrapper = document.createElement("div");
  wrapper.style.cssText = "border-radius: 6px; background: #1e1e2e; overflow: hidden; flex-shrink: 0;";
  const header = document.createElement("div");
  header.style.cssText = "display: flex; align-items: center; gap: 8px; padding: 8px 10px; cursor: pointer; user-select: none;";
  const chevron = document.createElement("span");
  chevron.style.cssText = "font-size: 10px; color: #888; transition: transform 0.2s ease; flex-shrink: 0;";
  chevron.textContent = "\u25B6";
  const titleEl = document.createElement("span");
  titleEl.style.cssText = "font-weight: 600; font-size: 13px; flex: 1;";
  titleEl.textContent = title;
  const badgeEl = document.createElement("span");
  badgeEl.style.cssText = "font-size: 10px; background: #3a3a4a; color: #aaa; padding: 1px 6px; border-radius: 8px; flex-shrink: 0;";
  badgeEl.textContent = badge != null ? badge : "0";
  header.appendChild(chevron);
  header.appendChild(titleEl);
  header.appendChild(badgeEl);
  const content = document.createElement("div");
  content.style.cssText = "max-height: 0; overflow: hidden; transition: max-height 0.3s ease; padding: 0 10px;";
  let isOpen = !!defaultOpen;
  function toggle() {
    isOpen = !isOpen;
    if (isOpen) {
      content.style.maxHeight = content.scrollHeight + 200 + "px";
      content.style.paddingBottom = "10px";
      chevron.style.transform = "rotate(90deg)";
    } else {
      content.style.maxHeight = "0";
      content.style.paddingBottom = "0";
      chevron.style.transform = "rotate(0deg)";
    }
  }
  function open() { if (!isOpen) toggle(); }
  function updateBadge(val) { badgeEl.textContent = String(val); }
  function refreshHeight() { if (isOpen) content.style.maxHeight = content.scrollHeight + 200 + "px"; }
  if (isOpen) {
    setTimeout(() => {
      content.style.maxHeight = content.scrollHeight + 200 + "px";
      content.style.paddingBottom = "10px";
      chevron.style.transform = "rotate(90deg)";
    }, 0);
  }
  header.onclick = toggle;
  wrapper.appendChild(header);
  wrapper.appendChild(content);
  return { wrapper, content, header, updateBadge, open, toggle, refreshHeight };
}

// ─── Status helpers ──────────────────────────────────────────────────────

function _statusBadge(status) {
  const colors = {
    ready: { bg: "#1a3a1a", color: "#7ed321", label: "Ready" },
    needs_mapping: { bg: "#3d2e00", color: "#f5a623", label: "Needs mapping" },
    invalid: { bg: "#3d1010", color: "#e05050", label: "Invalid" },
  };
  const s = colors[status] || { bg: "#2a2a2a", color: "#888", label: status || "Unknown" };
  const el = document.createElement("span");
  el.style.cssText = "font-size: 10px; background: " + s.bg + "; color: " + s.color + "; padding: 1px 6px; border-radius: 8px; flex-shrink: 0;";
  el.textContent = s.label;
  return el;
}

function _modelStackSummary(modelStack) {
  const parts = [];
  if (modelStack.checkpoint && modelStack.checkpoint.length) parts.push("CKPT:" + modelStack.checkpoint[0].substring(0, 20));
  if (modelStack.unet && modelStack.unet.length) parts.push("UNET:" + modelStack.unet[0].substring(0, 20));
  if (modelStack.clip && modelStack.clip.length) parts.push("CLIP:" + modelStack.clip[0].substring(0, 20));
  if (modelStack.vae && modelStack.vae.length) parts.push("VAE:" + modelStack.vae[0].substring(0, 20));
  if (modelStack.lora && modelStack.lora.length) parts.push("+" + modelStack.lora.length + " LoRA");
  return parts.join(" | ") || "No models";
}

// =========================================================================
// TAB 1: COMPARISON PROFILES
// =========================================================================

function buildProfilesTab() {
  const container = document.createElement("div");
  container.style.cssText = "font-size: 13px; color: var(--fg-color, #ddd); height: 100%; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden;";

  const scrollContent = document.createElement("div");
  scrollContent.style.cssText = "flex: 1; overflow-y: auto; min-height: 0; padding: 10px 16px 16px; display: flex; flex-direction: column; gap: 12px;";

  // ─── Save Current Workflow ─────────────────────────────────────────
  const saveSection = document.createElement("div");
  saveSection.style.cssText = "display: flex; flex-direction: column; gap: 6px; background: #1e1e2e; border-radius: 6px; padding: 10px;";

  const saveTitle = document.createElement("div");
  saveTitle.style.cssText = "font-weight: 600; font-size: 13px;";
  saveTitle.textContent = "Save Current Workflow as Profile";
  saveSection.appendChild(saveTitle);

  const saveDesc = document.createElement("div");
  saveDesc.style.cssText = "font-size: 11px; color: #888; line-height: 1.4;";
  saveDesc.textContent = "Saves the current ComfyUI workflow as a comparison profile for side-by-side testing.";
  saveSection.appendChild(saveDesc);

  const nameRow = document.createElement("div");
  nameRow.style.cssText = "display: flex; gap: 6px;";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = "Profile name (e.g. Flux2 Klein FP8)";
  nameInput.style.cssText = _inputStyle() + "flex: 1;";

  const saveBtn = document.createElement("button");
  saveBtn.textContent = "Save Profile";
  saveBtn.style.cssText = _btnStyle("primary") + "flex: 0 0 auto; width: auto;";

  nameRow.appendChild(nameInput);
  nameRow.appendChild(saveBtn);
  saveSection.appendChild(nameRow);

  const saveStatus = document.createElement("div");
  saveStatus.style.cssText = "font-size: 11px; color: #888; min-height: 14px;";
  saveSection.appendChild(saveStatus);

  saveBtn.onclick = async () => {
    const name = nameInput.value.trim();
    if (!name) {
      saveStatus.style.color = "#e05050";
      saveStatus.textContent = "Please enter a profile name.";
      return;
    }
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    saveStatus.style.color = "#f5a623";
    saveStatus.textContent = "Saving workflow...";

    try {
      const graph = app.graph;
      if (!graph) {
        throw new Error("No graph available");
      }
      const graphData = await app.graphToPrompt();
      if (!graphData || !graphData.output) {
        throw new Error("Could not export workflow as API JSON");
      }
      const workflowApi = graphData.output;
      const workflow = graphData.workflow || null;

      const resp = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, workflow_api: workflowApi, workflow }),
      });
      const data = await resp.json();
      if (data.status !== "ok") throw new Error(data.message || "Save failed");

      saveStatus.style.color = "#7ed321";
      saveStatus.textContent = 'Profile "' + name + '" saved!';
      nameInput.value = "";

      // Auto-detect slots
      const pid = data.profile.id;
      try {
        const detectResp = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + pid + "/detect-slots", { method: "POST" });
        const detectData = await detectResp.json();
        if (detectData.status === "ok" && detectData.candidates) {
          const slots = {};
          for (const [key, candidates] of Object.entries(detectData.candidates)) {
            if (candidates && candidates.length > 0) {
              const best = candidates[0];
              slots[key] = {
                node_id: best.node_id,
                path: best.path,
                field: best.field,
                class_type: best.class_type,
              };
            }
          }
          await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + pid + "/slots", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slots }),
          });
          saveStatus.textContent += " Slots auto-detected.";
        }
      } catch (detectErr) {
        console.log("[comfyui-modal] Slot auto-detect non-fatal:", detectErr);
      }

      _showToast("Profile saved!", "success");
      await refreshProfileList();
    } catch (e) {
      saveStatus.style.color = "#e05050";
      saveStatus.textContent = "Error: " + e.message;
      _showToast("Error saving profile: " + e.message, "error");
    }
    saveBtn.disabled = false;
    saveBtn.textContent = "Save Profile";
  };

  nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") saveBtn.click(); });

  scrollContent.appendChild(saveSection);

  // ─── Profile List ──────────────────────────────────────────────────
  const profileCollapsible = _createCollapsibleSection("Saved Profiles", { defaultOpen: true, badge: "..." });
  const profileListEl = document.createElement("div");
  profileListEl.style.cssText = "display: flex; flex-direction: column; gap: 6px;";
  profileCollapsible.content.appendChild(profileListEl);
  scrollContent.appendChild(profileCollapsible.wrapper);

  // ─── Open Mapping Assistant button ────────────────────────────────
  const mappingSection = document.createElement("div");
  mappingSection.style.cssText = "display: flex; flex-direction: column; gap: 6px; background: #1e1e2e; border-radius: 6px; padding: 10px;";

  const mappingTitle = document.createElement("div");
  mappingTitle.style.cssText = "font-weight: 600; font-size: 13px;";
  mappingTitle.textContent = "Mapping Assistant";
  mappingSection.appendChild(mappingTitle);

  const mappingDesc = document.createElement("div");
  mappingDesc.style.cssText = "font-size: 11px; color: #888; line-height: 1.4;";
  mappingDesc.textContent = "Select a profile below to configure which workflow nodes receive prompt, seed, resolution, and other shared inputs.";
  mappingSection.appendChild(mappingDesc);

  _mappingProfileSelect = document.createElement("select");
  _mappingProfileSelect.style.cssText = _inputStyle();
  _mappingProfileSelect.innerHTML = '<option value="">-- Select profile --</option>';
  mappingSection.appendChild(_mappingProfileSelect);

  const openMappingBtn = document.createElement("button");
  openMappingBtn.textContent = "Open Mapping Assistant";
  openMappingBtn.style.cssText = _btnStyle("primary");
  openMappingBtn.disabled = true;
  mappingSection.appendChild(openMappingBtn);

  const mappingPanel = document.createElement("div");
  mappingPanel.style.cssText = "display: none; flex-direction: column; gap: 10px;";

  openMappingBtn.onclick = () => {
    const pid = _mappingProfileSelect.value;
    if (!pid) return;
    openMappingAssistant(pid, mappingPanel, mappingSection);
  };

  _mappingProfileSelect.addEventListener("change", () => {
    openMappingBtn.disabled = !_mappingProfileSelect.value;
  });

  mappingSection.appendChild(mappingPanel);
  scrollContent.appendChild(mappingSection);

  _mappingPanelEl = mappingPanel;
  _mappingSectionEl = mappingSection;
  _profileListEl = profileListEl;
  _profileCollapsibleRef = profileCollapsible;

  container.appendChild(scrollContent);

  // Load profiles
  refreshProfileList().then(() => {
    refreshMappingDropdown();
  });

  return container;
}

// ─── Profile List Refresh ────────────────────────────────────────────────

async function refreshProfileList() {
  const listEl = _profileListEl;
  const collapsible = _profileCollapsibleRef;
  if (!listEl) return;
  listEl.innerHTML = '<div style="color: #888; font-size: 12px; padding: 8px 0;">Loading profiles...</div>';
  try {
    const resp = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles");
    const data = await resp.json();
    if (data.status !== "ok") throw new Error(data.message || "Failed to load");

    const profiles = data.profiles || [];
    listEl.innerHTML = "";

    if (profiles.length === 0) {
      listEl.innerHTML = '<div style="color: #666; font-size: 12px; padding: 8px 0;">No profiles saved yet. Open a workflow and click "Save Profile" above.</div>';
      if (collapsible) collapsible.updateBadge("0");
      return;
    }

    if (collapsible) collapsible.updateBadge(String(profiles.length));

    for (const profile of profiles) {
      const validation = profile.validation || {};
      const status = validation.status || "unknown";
      const warnings = validation.warnings || [];
      const errors = validation.errors || [];

      const card = document.createElement("div");
      card.style.cssText = "background: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 6px; padding: 8px; display: flex; flex-direction: column; gap: 4px;";

      // Header row: name + status badge
      const headerRow = document.createElement("div");
      headerRow.style.cssText = "display: flex; align-items: center; gap: 6px;";

      const nameEl = document.createElement("span");
      nameEl.style.cssText = "font-weight: 600; font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;";
      nameEl.textContent = profile.name || profile.id;

      headerRow.appendChild(nameEl);
      headerRow.appendChild(_statusBadge(status));
      card.appendChild(headerRow);

      // Model stack summary
      const stackSummary = _modelStackSummary(profile.model_stack || {});
      const stackEl = document.createElement("div");
      stackEl.style.cssText = "font-size: 10px; color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%;";
      stackEl.textContent = stackSummary;
      card.appendChild(stackEl);

      // Warnings / Errors
      if (warnings.length > 0) {
        const warnEl = document.createElement("div");
        warnEl.style.cssText = "font-size: 10px; color: #f5a623;";
        warnEl.textContent = "\u26A0 " + warnings.join("; ");
        card.appendChild(warnEl);
      }
      if (errors.length > 0) {
        const errEl = document.createElement("div");
        errEl.style.cssText = "font-size: 10px; color: #e05050;";
        errEl.textContent = "\u2717 " + errors.join("; ");
        card.appendChild(errEl);
      }

      // Capabilities
      const caps = profile.capabilities || {};
      const capParts = [];
      if (caps.txt2img) capParts.push("txt2img");
      if (caps.img2img) capParts.push("img2img");
      if (caps.supports_seed_override) capParts.push("seed");
      if (caps.supports_steps_override) capParts.push("steps");
      if (caps.supports_guidance_override) capParts.push("guidance");
      if (caps.supports_resolution_override) capParts.push("resolution");
      if (capParts.length > 0) {
        const capEl = document.createElement("div");
        capEl.style.cssText = "font-size: 10px; color: #666;";
        capEl.textContent = "Supports: " + capParts.join(", ");
        card.appendChild(capEl);
      }

      // Buttons
      const btnRow = document.createElement("div");
      btnRow.style.cssText = "display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap;";

      const openMappingBtn = document.createElement("button");
      openMappingBtn.textContent = "Mapping";
      openMappingBtn.style.cssText = _btnStyle() + "flex: 1; min-width: 60px; font-size: 11px; padding: 3px 6px;";
      openMappingBtn.onclick = () => { openMappingAssistant(profile.id, _mappingPanelEl, _mappingSectionEl); };

      const renameBtn = document.createElement("button");
      renameBtn.textContent = "Rename";
      renameBtn.style.cssText = _btnStyle() + "flex: 0 0 auto; font-size: 11px; padding: 3px 6px;";

      const duplicateBtn = document.createElement("button");
      duplicateBtn.textContent = "Duplicate";
      duplicateBtn.style.cssText = _btnStyle() + "flex: 0 0 auto; font-size: 11px; padding: 3px 6px;";

      const deleteBtn = document.createElement("button");
      deleteBtn.textContent = "Delete";
      deleteBtn.style.cssText = _btnStyle("danger") + "flex: 0 0 auto; font-size: 11px; padding: 3px 6px;";

      btnRow.appendChild(openMappingBtn);

      renameBtn.onclick = async () => {
        const newName = prompt("New name:", profile.name);
        if (!newName || newName.trim() === profile.name) return;
        try {
          const r = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + profile.id, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: newName.trim() }),
          });
          const d = await r.json();
          if (d.status === "ok") {
            _showToast("Profile renamed", "success");
            await refreshProfileList();
            refreshMappingDropdown();
          } else throw new Error(d.message);
        } catch (e) { _showToast("Rename failed: " + e.message, "error"); }
      };

      duplicateBtn.onclick = async () => {
        const newName = prompt("New profile name:", profile.name + " (copy)");
        if (!newName) return;
        try {
          const r = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + profile.id + "/duplicate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: newName.trim() }),
          });
          const d = await r.json();
          if (d.status === "ok") {
            _showToast("Profile duplicated", "success");
            await refreshProfileList();
            refreshMappingDropdown();
          } else throw new Error(d.message);
        } catch (e) { _showToast("Duplicate failed: " + e.message, "error"); }
      };

      deleteBtn.onclick = async () => {
        if (!(await _showConfirmDialog('Delete profile "' + (profile.name || profile.id) + '"?'))) return;
        try {
          const r = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + profile.id, { method: "DELETE" });
          const d = await r.json();
          if (d.status === "ok") {
            _showToast("Profile deleted", "success");
            await refreshProfileList();
            refreshMappingDropdown();
          } else throw new Error(d.message);
        } catch (e) { _showToast("Delete failed: " + e.message, "error"); }
      };

      btnRow.appendChild(renameBtn);
      btnRow.appendChild(duplicateBtn);
      btnRow.appendChild(deleteBtn);
      card.appendChild(btnRow);

      listEl.appendChild(card);
    }
  } catch (e) {
    listEl.textContent = "";
    const errDiv = document.createElement("div");
    errDiv.style.cssText = "color: #e05050; font-size: 12px;";
    errDiv.textContent = "Error loading profiles: " + e.message;
    listEl.appendChild(errDiv);
  }
}

// ─── Mapping Dropdown Refresh ────────────────────────────────────────────

async function refreshMappingDropdown() {
  const selectEl = _mappingProfileSelect;
  if (!selectEl) return;
  try {
    const resp = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles");
    const data = await resp.json();
    if (data.status !== "ok") return;
    const val = selectEl.value;
    selectEl.innerHTML = '<option value="">-- Select profile --</option>';
    for (const p of (data.profiles || [])) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name || p.id;
      selectEl.appendChild(opt);
    }
    if (val && Array.from(selectEl.options).some(o => o.value === val)) selectEl.value = val;
  } catch (e) {
    console.log("[comfyui-modal] Failed to refresh mapping dropdown:", e);
  }
}

// ─── Mapping Assistant ───────────────────────────────────────────────────

let _mappingPanelEl = null;
let _mappingSectionEl = null;
let _profileListEl = null;
let _profileCollapsibleRef = null;
let _mappingProfileSelect = null;
let _currentMappingProfileId = null;

async function openMappingAssistant(profileId, panelEl, sectionEl) {
  _currentMappingProfileId = profileId;
  panelEl.style.display = "flex";
  panelEl.innerHTML = '<div style="color: #888; font-size: 12px; padding: 8px 0;">Loading mapping data...</div>';

  try {
    const [profileResp, detectResp] = await Promise.all([
      api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + profileId),
      api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + profileId + "/detect-slots", { method: "POST" }),
    ]);

    const profileData = await profileResp.json();
    if (profileData.status !== "ok") throw new Error(profileData.message || "Profile not found");

    const profile = profileData.profile || {};
    let candidates = {};
    try {
      const detectData = await detectResp.json();
      if (detectData.status === "ok") {
        candidates = detectData.candidates || {};
      }
    } catch (detectErr) {
      console.log("[comfyui-modal] Slot detection non-fatal:", detectErr);
    }
    const slots = profile.slots || {};

    panelEl.innerHTML = "";

    // Title
    const title = document.createElement("div");
    title.style.cssText = "font-weight: 600; font-size: 12px; margin-bottom: 6px;";
    title.textContent = "Mapping: " + (profile.name || profileId);
    panelEl.appendChild(title);

    // Description
    const desc = document.createElement("div");
    desc.style.cssText = "font-size: 11px; color: #888; line-height: 1.4; margin-bottom: 8px;";
    desc.innerHTML = 'Configure where shared comparison inputs are injected. Use <code style="color: #ddd;">@prompt</code>, <code style="color: #ddd;">@seed</code>, <code style="color: #ddd;">@width</code>, etc. in node titles for automatic detection.';
    panelEl.appendChild(desc);

    // Slot mappings
    const slotKeys = ["prompt", "negative_prompt", "seed", "steps", "guidance", "width", "height", "input_image"];
    const slotLabels = {
      prompt: "Prompt *",
      negative_prompt: "Negative Prompt",
      seed: "Seed *",
      steps: "Steps",
      guidance: "Guidance/CFG",
      width: "Width",
      height: "Height",
      input_image: "Input Image",
    };
    const requiredSlots = ["prompt", "seed"];

    const mappingForm = document.createElement("div");
    mappingForm.style.cssText = "display: flex; flex-direction: column; gap: 6px;";

    for (const key of slotKeys) {
      const currentSlot = slots[key] || {};
      const slotCandidates = candidates[key] || [];

      const row = document.createElement("div");
      row.style.cssText = "background: #222; border: 1px solid #333; border-radius: 4px; padding: 6px;";

      const header = document.createElement("div");
      header.style.cssText = "display: flex; align-items: center; gap: 6px; margin-bottom: 4px;";

      const enabledToggle = document.createElement("input");
      enabledToggle.type = "checkbox";
      enabledToggle.checked = !!currentSlot.node_id;
      enabledToggle.style.cssText = "width: 14px; height: 14px; accent-color: #3a6fcc; flex-shrink: 0;";

      const label = document.createElement("span");
      label.style.cssText = "font-size: 12px; font-weight: 600; flex: 1;";
      label.textContent = slotLabels[key] || key;
      if (requiredSlots.includes(key)) {
        const req = document.createElement("span");
        req.style.cssText = "font-size: 10px; color: #e05050; margin-left: 4px;";
        req.textContent = "(required)";
        label.appendChild(req);
      }

      const candidateInfo = document.createElement("span");
      candidateInfo.style.cssText = "font-size: 10px; color: #888; flex-shrink: 0;";
      if (currentSlot.node_id) {
        candidateInfo.textContent = "node " + currentSlot.node_id + " (" + (currentSlot.field || "") + ")";
      } else {
        candidateInfo.textContent = slotCandidates.length > 0 ? slotCandidates.length + " candidate(s)" : "No candidates";
      }

      header.appendChild(enabledToggle);
      header.appendChild(label);
      header.appendChild(candidateInfo);
      row.appendChild(header);

      // Dropdown
      const select = document.createElement("select");
      select.style.cssText = _inputStyle() + "margin-bottom: 4px; display: " + (enabledToggle.checked ? "" : "none") + ";";
      select.innerHTML = '<option value="">-- None --</option>';

      for (const c of slotCandidates) {
        const opt = document.createElement("option");
        opt.value = JSON.stringify({ node_id: c.node_id, path: c.path, field: c.field });
        opt.textContent = "node " + c.node_id + " - " + (c.class_type || "?") + "." + (c.field || "?") + " (" + (c.reason || "") + ")";
        // Check if this matches current slot
        if (currentSlot.node_id === c.node_id && currentSlot.field === c.field) {
          opt.selected = true;
        }
        select.appendChild(opt);
      }

      // If current slot has a node_id not in candidates, add it manually
      if (currentSlot.node_id && !slotCandidates.some(c => c.node_id === currentSlot.node_id)) {
        const opt = document.createElement("option");
        opt.value = JSON.stringify({ node_id: currentSlot.node_id, path: currentSlot.path, field: currentSlot.field });
        opt.textContent = "node " + currentSlot.node_id + " - " + (currentSlot.class_type || "?") + "." + (currentSlot.field || "?") + " (current)";
        opt.selected = true;
        select.appendChild(opt);
      }

      row.appendChild(select);

      enabledToggle.addEventListener("change", () => {
        select.style.display = enabledToggle.checked ? "" : "none";
        if (!enabledToggle.checked) select.value = "";
      });

      mappingForm.appendChild(row);
    }

    panelEl.appendChild(mappingForm);

    // Save button
    const saveMappingBtn = document.createElement("button");
    saveMappingBtn.textContent = "Save Mappings";
    saveMappingBtn.style.cssText = _btnStyle("primary") + "margin-top: 8px;";
    saveMappingBtn.onclick = async () => {
      const slotsData = {};
      const rows = mappingForm.querySelectorAll("div[style]");
      let idx = 0;
      for (const key of slotKeys) {
        const row = mappingForm.children[idx];
        if (!row) { idx++; continue; }
        const toggle = row.querySelector("input[type=checkbox]");
        const select = row.querySelector("select");
        if (toggle && select) {
          if (toggle.checked && select.value) {
            try {
              const parsed = JSON.parse(select.value);
              slotsData[key] = parsed;
            } catch (e) {
              slotsData[key] = { node_id: select.value };
            }
          } else if (!toggle.checked) {
            // Skip this slot
          }
        }
        idx++;
      }

      try {
        const r = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + profileId + "/slots", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slots: slotsData }),
        });
        const d = await r.json();
        if (d.status === "ok") {
          _showToast("Mappings saved", "success");
          refreshProfileList();
        } else throw new Error(d.message);
      } catch (e) {
        _showToast("Error saving mappings: " + e.message, "error");
      }
    };

    panelEl.appendChild(saveMappingBtn);

    // Close button
    const closeMappingBtn = document.createElement("button");
    closeMappingBtn.textContent = "Close";
    closeMappingBtn.style.cssText = _btnStyle() + "margin-top: 4px;";
    closeMappingBtn.onclick = () => {
      panelEl.style.display = "none";
      panelEl.innerHTML = "";
    };
    panelEl.appendChild(closeMappingBtn);

  } catch (e) {
    panelEl.textContent = "";
    const errDiv = document.createElement("div");
    errDiv.style.cssText = "color: #e05050; font-size: 12px;";
    errDiv.textContent = "Error: " + e.message;
    panelEl.appendChild(errDiv);
  }
}

// =========================================================================
// TAB 2: COMPARISON RUNNER
// =========================================================================

function buildRunnerTab() {
  const container = document.createElement("div");
  container.style.cssText = "font-size: 13px; color: var(--fg-color, #ddd); height: 100%; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden;";

  const scrollContent = document.createElement("div");
  scrollContent.style.cssText = "flex: 1; overflow-y: auto; min-height: 0; padding: 10px 16px 16px; display: flex; flex-direction: column; gap: 12px;";

  // ─── Shared Inputs ─────────────────────────────────────────────────
  const inputsSection = document.createElement("div");
  inputsSection.style.cssText = "display: flex; flex-direction: column; gap: 6px; background: #1e1e2e; border-radius: 6px; padding: 10px;";

  const inputsTitle = document.createElement("div");
  inputsTitle.style.cssText = "font-weight: 600; font-size: 13px;";
  inputsTitle.textContent = "Shared Inputs";
  inputsSection.appendChild(inputsTitle);

  // Load saved inputs
  let savedInputs = {};
  try { savedInputs = JSON.parse(localStorage.getItem(STORAGE_RUNNER_INPUTS)) || {}; } catch (e) {}

  // Prompt
  const promptLabel = document.createElement("div");
  promptLabel.style.cssText = "font-size: 12px; color: #aaa; font-weight: 600;";
  promptLabel.textContent = "Prompt";
  inputsSection.appendChild(promptLabel);

  const promptInput = document.createElement("textarea");
  promptInput.placeholder = "Enter shared prompt...";
  promptInput.value = savedInputs.prompt || "";
  promptInput.style.cssText = _inputStyle() + "min-height: 60px; resize: vertical; font-family: inherit;";
  inputsSection.appendChild(promptInput);

  // Negative prompt
  const negLabel = document.createElement("div");
  negLabel.style.cssText = "font-size: 12px; color: #aaa; font-weight: 600; margin-top: 4px;";
  negLabel.textContent = "Negative Prompt (optional)";
  inputsSection.appendChild(negLabel);

  const negInput = document.createElement("textarea");
  negInput.placeholder = "Shared negative prompt...";
  negInput.value = savedInputs.negative_prompt || "";
  negInput.style.cssText = _inputStyle() + "min-height: 40px; resize: vertical; font-family: inherit;";
  inputsSection.appendChild(negInput);

  // Seed row
  const seedRow = document.createElement("div");
  seedRow.style.cssText = "display: flex; align-items: center; gap: 6px; margin-top: 4px;";

  const seedLabel = document.createElement("span");
  seedLabel.style.cssText = "font-size: 12px; color: #aaa; font-weight: 600; flex-shrink: 0;";
  seedLabel.textContent = "Seed";

  const seedInput = document.createElement("input");
  seedInput.type = "number";
  seedInput.value = savedInputs.seed != null ? savedInputs.seed : Math.floor(Math.random() * 2147483647);
  seedInput.style.cssText = _inputStyle() + "flex: 1;";
  seedInput.min = "0";
  seedInput.max = "2147483647";

  const randomizeBtn = document.createElement("button");
  randomizeBtn.textContent = "\uD83C\uDFB2";
  randomizeBtn.title = "Randomize seed";
  randomizeBtn.style.cssText = _btnStyle() + "flex: 0 0 auto; width: 30px; padding: 4px; font-size: 14px;";

  randomizeBtn.onclick = () => {
    seedInput.value = Math.floor(Math.random() * 2147483647);
  };

  seedRow.appendChild(seedLabel);
  seedRow.appendChild(seedInput);
  seedRow.appendChild(randomizeBtn);
  inputsSection.appendChild(seedRow);

  // Resolution row
  const resRow = document.createElement("div");
  resRow.style.cssText = "display: flex; align-items: center; gap: 6px; margin-top: 4px;";

  const widthInput = document.createElement("input");
  widthInput.type = "number";
  widthInput.value = savedInputs.width || 1024;
  widthInput.placeholder = "Width";
  widthInput.style.cssText = _inputStyle() + "flex: 1;";
  widthInput.min = "64";
  widthInput.max = "8192";

  const resSep = document.createElement("span");
  resSep.style.cssText = "color: #666; font-size: 14px; flex-shrink: 0;";
  resSep.textContent = "\u00D7";

  const heightInput = document.createElement("input");
  heightInput.type = "number";
  heightInput.value = savedInputs.height || 1024;
  heightInput.placeholder = "Height";
  heightInput.style.cssText = _inputStyle() + "flex: 1;";
  heightInput.min = "64";
  heightInput.max = "8192";

  resRow.appendChild(widthInput);
  resRow.appendChild(resSep);
  resRow.appendChild(heightInput);
  inputsSection.appendChild(resRow);

  // Steps
  const stepsRow = document.createElement("div");
  stepsRow.style.cssText = "display: flex; align-items: center; gap: 6px; margin-top: 4px;";

  const stepsLabel = document.createElement("span");
  stepsLabel.style.cssText = "font-size: 12px; color: #aaa; font-weight: 600; flex-shrink: 0; width: 50px;";
  stepsLabel.textContent = "Steps";

  const stepsInput = document.createElement("input");
  stepsInput.type = "number";
  stepsInput.value = savedInputs.steps || 30;
  stepsInput.style.cssText = _inputStyle() + "flex: 1;";
  stepsInput.min = "1";
  stepsInput.max = "200";

  stepsRow.appendChild(stepsLabel);
  stepsRow.appendChild(stepsInput);
  inputsSection.appendChild(stepsRow);

  // Guidance/CFG
  const guidanceRow = document.createElement("div");
  guidanceRow.style.cssText = "display: flex; align-items: center; gap: 6px; margin-top: 4px;";

  const guidanceLabel = document.createElement("span");
  guidanceLabel.style.cssText = "font-size: 12px; color: #aaa; font-weight: 600; flex-shrink: 0; width: 50px;";
  guidanceLabel.textContent = "Guidance";

  const guidanceInput = document.createElement("input");
  guidanceInput.type = "number";
  guidanceInput.value = savedInputs.guidance || 3.5;
  guidanceInput.style.cssText = _inputStyle() + "flex: 1;";
  guidanceInput.min = "0";
  guidanceInput.max = "100";
  guidanceInput.step = "0.5";

  guidanceRow.appendChild(guidanceLabel);
  guidanceRow.appendChild(guidanceInput);
  inputsSection.appendChild(guidanceRow);

  scrollContent.appendChild(inputsSection);

  // ─── Execution Mode ────────────────────────────────────────────────
  let savedConfig = {};
  try { savedConfig = JSON.parse(localStorage.getItem(STORAGE_RUNNER_CONFIG)) || {}; } catch (e) {}

  const modeSection = document.createElement("div");
  modeSection.style.cssText = "display: flex; flex-direction: column; gap: 6px; background: #1e1e2e; border-radius: 6px; padding: 10px;";

  const modeTitle = document.createElement("div");
  modeTitle.style.cssText = "font-weight: 600; font-size: 13px;";
  modeTitle.textContent = "Execution";
  modeSection.appendChild(modeTitle);

  const modeToggle = document.createElement("div");
  modeToggle.style.cssText = "display: flex; border-radius: 6px; overflow: hidden; border: 1px solid #444;";

  const isParallel = savedConfig.execution_mode === "parallel";
  const seqBtn = document.createElement("button");
  seqBtn.textContent = "Sequential";
  seqBtn.style.cssText = _segmentBtnStyle(!isParallel);
  const parBtn = document.createElement("button");
  parBtn.textContent = "Parallel";
  parBtn.style.cssText = _segmentBtnStyle(isParallel);

  function updateMode(parallel) {
    seqBtn.style.cssText = _segmentBtnStyle(!parallel);
    parBtn.style.cssText = _segmentBtnStyle(parallel);
    maxParallelRow.style.display = parallel ? "" : "none";
  }

  seqBtn.onclick = () => updateMode(false);
  parBtn.onclick = () => updateMode(true);

  modeToggle.appendChild(seqBtn);
  modeToggle.appendChild(parBtn);
  modeSection.appendChild(modeToggle);

  // Max parallel jobs
  const maxParallelRow = document.createElement("div");
  maxParallelRow.style.cssText = "display: " + (isParallel ? "" : "none") + "; align-items: center; gap: 6px;";

  const maxParLabel = document.createElement("span");
  maxParLabel.style.cssText = "font-size: 12px; color: #aaa; font-weight: 600; flex-shrink: 0;";
  maxParLabel.textContent = "Max parallel jobs";

  const maxParInput = document.createElement("input");
  maxParInput.type = "number";
  maxParInput.value = savedConfig.max_parallel_jobs || 2;
  maxParInput.style.cssText = _inputStyle() + "flex: 0 0 60px;";
  maxParInput.min = "1";
  maxParInput.max = "10";

  maxParallelRow.appendChild(maxParLabel);
  maxParallelRow.appendChild(maxParInput);
  modeSection.appendChild(maxParallelRow);

  scrollContent.appendChild(modeSection);

  // ─── Profile Selection ─────────────────────────────────────────────
  const profileSection = document.createElement("div");
  profileSection.style.cssText = "display: flex; flex-direction: column; gap: 6px; background: #1e1e2e; border-radius: 6px; padding: 10px;";

  const profileTitleRow = document.createElement("div");
  profileTitleRow.style.cssText = "display: flex; align-items: center; gap: 6px;";

  const profileTitle = document.createElement("span");
  profileTitle.style.cssText = "font-weight: 600; font-size: 13px; flex: 1;";
  profileTitle.textContent = "Select Profiles";

  const refreshProfilesBtn = document.createElement("button");
  refreshProfilesBtn.textContent = "\u21BA";
  refreshProfilesBtn.title = "Refresh profiles";
  refreshProfilesBtn.style.cssText = _btnStyle() + "flex: 0 0 auto; width: 28px; padding: 2px; font-size: 14px;";

  profileTitleRow.appendChild(profileTitle);
  profileTitleRow.appendChild(refreshProfilesBtn);
  profileSection.appendChild(profileTitleRow);

  const profileCheckboxList = document.createElement("div");
  profileCheckboxList.style.cssText = "display: flex; flex-direction: column; gap: 4px; max-height: 300px; overflow-y: auto;";

  let selectedProfiles = new Set();
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_SELECTED_PROFILES)) || [];
    selectedProfiles = new Set(saved);
  } catch (e) {}

  // Per-profile override (skip shared value, use workflow's own)
  let perProfileOverrides = {};
  try {
    var pp = savedConfig.per_profile_overrides || {};
    perProfileOverrides = JSON.parse(JSON.stringify(pp));
  } catch (e) {}

  function savePerProfileOverrides() {
    var cfg = JSON.parse(localStorage.getItem(STORAGE_RUNNER_CONFIG) || "{}");
    cfg.per_profile_overrides = perProfileOverrides;
    localStorage.setItem(STORAGE_RUNNER_CONFIG, JSON.stringify(cfg));
  }

  function _overrideToggle(pid, slotKeys, label) {
    if (!Array.isArray(slotKeys)) slotKeys = [slotKeys];
    var div = document.createElement("div");
    div.style.cssText = "display: flex; align-items: center; gap: 4px;";

    function _isAnySkipped() {
      if (!perProfileOverrides[pid] || !perProfileOverrides[pid].skip_slots) return false;
      return slotKeys.some(function (k) { return perProfileOverrides[pid].skip_slots.indexOf(k) !== -1; });
    }

    var isSkipped = _isAnySkipped();

    var btn = document.createElement("button");
    btn.textContent = isSkipped ? "Use own " + label : "Shared " + label;
    btn.title = isSkipped ? "Use this profile's default " + label : "Override with shared " + label;
    btn.style.cssText = "background: " + (isSkipped ? "#3d2e00" : "#2a2a2a") + "; border: 1px solid " + (isSkipped ? "#f5a623" : "#444") + "; color: " + (isSkipped ? "#f5a623" : "#888") + "; padding: 2px 6px; border-radius: 3px; cursor: pointer; font-size: 10px; flex: 1; white-space: nowrap;";

    btn.onclick = function () {
      if (!perProfileOverrides[pid]) perProfileOverrides[pid] = { skip_slots: [] };
      var arr = perProfileOverrides[pid].skip_slots;
      var currentlySkipped = slotKeys.some(function (k) { return arr.indexOf(k) !== -1; });
      if (currentlySkipped) {
        // Remove all of these slot keys from skip
        perProfileOverrides[pid].skip_slots = arr.filter(function (s) { return slotKeys.indexOf(s) === -1; });
      } else {
        // Add all of these slot keys to skip
        slotKeys.forEach(function (k) {
          if (arr.indexOf(k) === -1) arr.push(k);
        });
      }
      savePerProfileOverrides();
      var newSkipped = _isAnySkipped();
      btn.textContent = newSkipped ? "Use own " + label : "Shared " + label;
      btn.title = newSkipped ? "Use this profile's default " + label : "Override with shared " + label;
      btn.style.cssText = "background: " + (newSkipped ? "#3d2e00" : "#2a2a2a") + "; border: 1px solid " + (newSkipped ? "#f5a623" : "#444") + "; color: " + (newSkipped ? "#f5a623" : "#888") + "; padding: 2px 6px; border-radius: 3px; cursor: pointer; font-size: 10px; flex: 1; white-space: nowrap;";
    };

    div.appendChild(btn);
    return div;
  }

  async function loadProfileCheckboxes() {
    profileCheckboxList.innerHTML = '<div style="color: #888; font-size: 12px; padding: 4px 0;">Loading...</div>';
    try {
      const resp = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles");
      const data = await resp.json();
      if (data.status !== "ok") throw new Error(data.message);
      profileCheckboxList.innerHTML = "";
      const profiles = data.profiles || [];
      if (profiles.length === 0) {
        profileCheckboxList.innerHTML = '<div style="color: #666; font-size: 12px; padding: 4px 0;">No profiles. Save a workflow as a profile first.</div>';
        return;
      }
      for (const p of profiles) {
        const validation = p.validation || {};
        const status = validation.status || "unknown";
        const isReady = status === "ready";
        const disabled = status === "invalid" && !isReady;
        const warnings = validation.warnings || [];

        const card = document.createElement("div");
        card.style.cssText = "background: #222; border: 1px solid #333; border-radius: 4px; overflow: hidden;";

        const row = document.createElement("label");
        row.style.cssText = "display: flex; align-items: center; gap: 6px; padding: 4px 6px; cursor: " + (disabled ? "not-allowed" : "pointer") + "; opacity: " + (disabled ? 0.5 : 1) + ";";

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = selectedProfiles.has(p.id) && !disabled;
        cb.disabled = disabled;
        cb.style.cssText = "width: 14px; height: 14px; accent-color: #3a6fcc; flex-shrink: 0;";

        cb.addEventListener("change", function () {
          if (cb.checked) selectedProfiles.add(p.id);
          else selectedProfiles.delete(p.id);
          localStorage.setItem(STORAGE_SELECTED_PROFILES, JSON.stringify(Array.from(selectedProfiles)));
        });

        const nameEl = document.createElement("span");
        nameEl.style.cssText = "font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;";
        nameEl.textContent = p.name || p.id;

        const stackEl = document.createElement("span");
        stackEl.style.cssText = "font-size: 10px; color: #666; flex-shrink: 0; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;";
        stackEl.textContent = _modelStackSummary(p.model_stack || {});

        row.appendChild(cb);
        row.appendChild(nameEl);
        row.appendChild(_statusBadge(status));
        row.appendChild(stackEl);

        if (warnings.length > 0 && isReady) {
          const warnIcon = document.createElement("span");
          warnIcon.style.cssText = "font-size: 10px; color: #f5a623; flex-shrink: 0;";
          warnIcon.textContent = "\u26A0";
          warnIcon.title = warnings.join("; ");
          row.appendChild(warnIcon);
        }

        card.appendChild(row);

        // Per-profile override toggles (visible when checked)
        var overrideArea = document.createElement("div");
        overrideArea.style.cssText = "display: " + (cb.checked ? "" : "none") + "; flex-direction: column; gap: 3px; padding: 4px 8px 6px 24px; border-top: 1px solid #333; margin-top: 2px;";

        var overrideLabel = document.createElement("div");
        overrideLabel.style.cssText = "font-size: 10px; color: #666; margin-bottom: 2px;";
        overrideLabel.textContent = "Override shared:";
        overrideArea.appendChild(overrideLabel);

        var toggleRow = document.createElement("div");
        toggleRow.style.cssText = "display: flex; gap: 4px;";

        var caps = p.capabilities || {};
        var hasSteps = caps.supports_steps_override;
        var hasGuidance = caps.supports_guidance_override;
        var hasResolution = caps.supports_resolution_override;

        if (hasSteps) toggleRow.appendChild(_overrideToggle(p.id, ["steps"], "Steps"));
        if (hasGuidance) toggleRow.appendChild(_overrideToggle(p.id, ["guidance"], "Guidance"));
        if (hasResolution) toggleRow.appendChild(_overrideToggle(p.id, ["width", "height"], "Resolution"));

        overrideArea.appendChild(toggleRow);
        card.appendChild(overrideArea);

        // Show/hide override area when checkbox changes
        cb.addEventListener("change", function () {
          overrideArea.style.display = cb.checked ? "" : "none";
        });

        profileCheckboxList.appendChild(card);
      }
    } catch (e) {
      profileCheckboxList.textContent = "";
      const errDiv = document.createElement("div");
      errDiv.style.cssText = "color: #e05050; font-size: 12px;";
      errDiv.textContent = "Error: " + e.message;
      profileCheckboxList.appendChild(errDiv);
    }
  }

  refreshProfilesBtn.onclick = loadProfileCheckboxes;

  profileSection.appendChild(profileCheckboxList);
  scrollContent.appendChild(profileSection);

  // ─── Run Button ────────────────────────────────────────────────────
  const runBtn = document.createElement("button");
  runBtn.textContent = "Run Comparison";
  runBtn.style.cssText = _btnStyle("primary") + "padding: 10px; font-size: 14px;";
  runBtn.onclick = async () => {
    const profileIds = Array.from(selectedProfiles);
    if (profileIds.length === 0) {
      _showToast("Select at least one profile", "error");
      return;
    }

    const inputs = {
      prompt: promptInput.value.trim(),
      negative_prompt: negInput.value.trim() || "",
      seed: parseInt(seedInput.value, 10) || 0,
      width: parseInt(widthInput.value, 10) || 1024,
      height: parseInt(heightInput.value, 10) || 1024,
      steps: parseInt(stepsInput.value, 10) || null,
      guidance: parseFloat(guidanceInput.value) || null,
    };

    const mode = parBtn.style.background === "rgb(58, 111, 204)" ? "parallel" : "sequential";
    const maxPar = parseInt(maxParInput.value, 10) || 2;

    // Save inputs to localStorage
    localStorage.setItem(STORAGE_RUNNER_INPUTS, JSON.stringify(inputs));
    localStorage.setItem(STORAGE_RUNNER_CONFIG, JSON.stringify({
      execution_mode: mode,
      max_parallel_jobs: maxPar,
    }));

    // Get output settings from modal-settings
    const outputOpts = window._comfyModalOutputOptions || {};

    runBtn.disabled = true;
    runBtn.textContent = "Running...";
    _showToast("Starting comparison with " + profileIds.length + " profile(s)", "info");

    try {
      // Normalise overrides: width skip implies height skip too
      var finalOverrides = JSON.parse(JSON.stringify(perProfileOverrides));
      for (var pid in finalOverrides) {
        var skip = finalOverrides[pid].skip_slots;
        if (skip && skip.indexOf("width") !== -1 && skip.indexOf("height") === -1) {
          skip.push("height");
        }
      }

      const resp = await api.fetchApi(MODAL_PREFIX + "/comparison/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile_ids: profileIds,
          ...inputs,
          execution_mode: mode,
          max_parallel_jobs: maxPar,
          per_profile_overrides: finalOverrides,
          output_format: outputOpts.output_format || "original",
          quality: outputOpts.quality || 75,
          webp_lossless_compression: outputOpts.webp_lossless_compression || "balanced",
          auto_save_local: outputOpts.auto_save_local || false,
          save_folder: outputOpts.save_folder || "",
          save_metadata_sidecar: outputOpts.save_metadata_sidecar !== false,
        }),
      });
      const data = await resp.json();
      if (data.status !== "ok") throw new Error(data.message || "Comparison failed");

      _showToast("Comparison complete!", "success");

      // Switch to gallery view
      buildGallery(container, data);
    } catch (e) {
      _showToast("Comparison error: " + e.message, "error");
    }
    runBtn.disabled = false;
    runBtn.textContent = "Run Comparison";
  };

  scrollContent.appendChild(runBtn);

  // Load profiles
  loadProfileCheckboxes();

  container.appendChild(scrollContent);
  return container;
}

// =========================================================================
// GALLERY
// =========================================================================

function buildGallery(container, comparisonData) {
  const comparisonId = comparisonData.comparison_id;
  const results = comparisonData.results || [];
  const errors = comparisonData.errors || [];

  // Clear container and build gallery
  container.innerHTML = "";

  const scrollContent = document.createElement("div");
  scrollContent.style.cssText = "flex: 1; overflow-y: auto; min-height: 0; padding: 10px 16px 16px; display: flex; flex-direction: column; gap: 12px;";

  // Header
  const headerRow = document.createElement("div");
  headerRow.style.cssText = "display: flex; align-items: center; gap: 8px;";

  const title = document.createElement("span");
  title.style.cssText = "font-weight: 600; font-size: 14px; flex: 1;";
  title.textContent = "Comparison Results";

  const backBtn = document.createElement("button");
  backBtn.textContent = "\u2190 Back";
  backBtn.style.cssText = _btnStyle() + "flex: 0 0 auto; width: auto;";
  backBtn.onclick = () => {
    const newRunner = buildRunnerTab();
    container.parentNode.replaceChild(newRunner, container);
  };

  headerRow.appendChild(title);
  headerRow.appendChild(backBtn);
  scrollContent.appendChild(headerRow);

  // Summary
  const summary = document.createElement("div");
  summary.style.cssText = "font-size: 11px; color: #888; line-height: 1.5; background: #1e1e2e; border-radius: 6px; padding: 8px;";
  summary.textContent = "Seed: " + comparisonData.seed + " | Resolution: " + (comparisonData.width || "?") + "\u00D7" + (comparisonData.height || "?");
  if (comparisonData.comparison_id) {
    summary.appendChild(document.createElement("br"));
    const idSpan = document.createElement("span");
    idSpan.style.cssText = "font-size: 10px; color: #666;";
    idSpan.textContent = "ID: " + comparisonData.comparison_id;
    summary.appendChild(idSpan);
  }
  scrollContent.appendChild(summary);

  // Success results
  if (results.length > 0) {
    const resultsTitle = document.createElement("div");
    resultsTitle.style.cssText = "font-weight: 600; font-size: 12px; color: #7ed321;";
    resultsTitle.textContent = results.length + " profile(s) completed";
    scrollContent.appendChild(resultsTitle);

    const gallery = document.createElement("div");
    gallery.style.cssText = "display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px;";

    for (const result of results) {
      const imageData = result.image_data_b64;
      if (!imageData) continue;

      const card = document.createElement("div");
      card.style.cssText = "background: #1e1e2e; border: 1px solid #333; border-radius: 6px; overflow: hidden; display: flex; flex-direction: column;";

      const img = document.createElement("img");
      img.src = "data:" + (result.mime_type || "image/png") + ";base64," + imageData;
      img.style.cssText = "width: 100%; height: auto; display: block;";
      card.appendChild(img);

      const meta = document.createElement("div");
      meta.style.cssText = "padding: 6px; display: flex; flex-direction: column; gap: 2px;";

      const pname = document.createElement("div");
      pname.style.cssText = "font-size: 11px; font-weight: 600;";
      pname.textContent = result.profile_name || result.profile_id;
      meta.appendChild(pname);

      const details = document.createElement("div");
      details.style.cssText = "font-size: 10px; color: #888;";
      const parts = [];
      if (result.seed != null) parts.push("Seed: " + result.seed);
      if (result.wall_time_sec != null) parts.push((result.wall_time_sec).toFixed(1) + "s");
      details.textContent = parts.join(" | ");
      meta.appendChild(details);

      // Model stack
      if (result.model_stack) {
        const ms = document.createElement("div");
        ms.style.cssText = "font-size: 9px; color: #666; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;";
        ms.textContent = _modelStackSummary(result.model_stack);
        meta.appendChild(ms);
      }

      // Buttons
      const btnRow = document.createElement("div");
      btnRow.style.cssText = "display: flex; gap: 4px; margin-top: 4px;";

      if (result.output_path) {
        const openBtn = document.createElement("button");
        openBtn.textContent = "Open";
        openBtn.style.cssText = _btnStyle() + "flex: 1; font-size: 10px; padding: 2px 4px;";
        openBtn.onclick = () => {
          api.fetchApi(MODAL_PREFIX + "/open-folder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: result.output_path }),
          });
        };
        btnRow.appendChild(openBtn);
      }

      const metaBtn = document.createElement("button");
      metaBtn.textContent = "Copy Meta";
      metaBtn.style.cssText = _btnStyle() + "flex: 1; font-size: 10px; padding: 2px 4px;";
      metaBtn.onclick = () => {
        const metaData = {
          profile: result.profile_name || result.profile_id,
          seed: result.seed,
          model_stack: result.model_stack,
          wall_time_sec: result.wall_time_sec,
        };
        navigator.clipboard.writeText(JSON.stringify(metaData, null, 2)).then(() => {
          _showToast("Metadata copied", "success");
        }).catch(() => {});
      };
      btnRow.appendChild(metaBtn);

      meta.appendChild(btnRow);
      card.appendChild(meta);
      gallery.appendChild(card);
    }

    scrollContent.appendChild(gallery);
  }

  // Errors
  if (errors.length > 0) {
    const errTitle = document.createElement("div");
    errTitle.style.cssText = "font-weight: 600; font-size: 12px; color: #e05050; margin-top: 8px;";
    errTitle.textContent = errors.length + " profile(s) failed";
    scrollContent.appendChild(errTitle);

    for (const err of errors) {
      const errCard = document.createElement("div");
      errCard.style.cssText = "background: #2a1a1a; border: 1px solid #3d1010; border-radius: 4px; padding: 6px; font-size: 11px;";
      errCard.textContent = "";
      const nameStrong = document.createElement("strong");
      nameStrong.style.color = "#e05050";
      nameStrong.textContent = (err.profile_name || err.profile_id || "Unknown") + ": ";
      errCard.appendChild(nameStrong);
      errCard.appendChild(document.createTextNode(" "));
      const errMsgSpan = document.createElement("span");
      errMsgSpan.style.color = "#aaa";
      errMsgSpan.textContent = err.error || "Unknown error";
      errCard.appendChild(errMsgSpan);
      scrollContent.appendChild(errCard);
    }
  }

  container.appendChild(scrollContent);
}

// =========================================================================
// EXTENSION REGISTRATION
// =========================================================================

// ─── Right-click context menu (node → slot mapping) ───────────────

function _inputNamesFromNode(node) {
  // LiteGraph stores node.inputs as an array of {name, type, link}.
  const arr = node && node.inputs;
  if (!Array.isArray(arr)) return [];
  return arr.map(function (i) { return i && typeof i === "object" ? i.name : ""; }).filter(Boolean);
}

async function _resolveProfileNode(profileId, classType, title) {
  // Load the profile's saved workflow node list and return the
  // best-matching node id (string).  Matches by exact title first,
  // then by class_type.
  try {
    var r = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + profileId + "/workflow/nodes");
    var d = await r.json();
    if (d.status !== "ok" || !d.nodes) return null;
    var nodes = d.nodes;  // {node_id: {class_type, title}}
    // Exact title match
    for (var nid in nodes) {
      var nt = nodes[nid].title || "";
      if (nt && title && nt.toLowerCase() === title.toLowerCase()) {
        return String(nid);
      }
    }
    // Class_type match (first one wins)
    for (var nid in nodes) {
      if (nodes[nid].class_type && classType && nodes[nid].class_type === classType) {
        return String(nid);
      }
    }
    return null;
  } catch (e) {
    return null;
  }
}

let _originalGetNodeMenuOptions = null;

function _initContextMenu() {
  if (!app?.canvas?.getNodeMenuOptions) return;
  // Guard: do not double-wrap
  if (_originalGetNodeMenuOptions) return;

  _originalGetNodeMenuOptions = app.canvas.getNodeMenuOptions.bind(app.canvas);
  app.canvas.getNodeMenuOptions = function (node) {
    var options = _originalGetNodeMenuOptions(node);

    var slotLabels = {
      prompt: "Prompt",
      negative_prompt: "Negative Prompt",
      seed: "Seed",
      steps: "Steps",
      guidance: "Guidance / CFG",
      width: "Width",
      height: "Height",
      input_image: "Input Image",
    };

    var slotItems = Object.entries(slotLabels).map(function (entry) {
      var key = entry[0];
      var label = entry[1];
      return {
        content: label,
        callback: async function () {
          if (!node) return;
          var classType = node.type || "";
          var title = node.title || "";

          // Input names from the LiteGraph node (array of {name, type})
          var names = _inputNamesFromNode(node);
          var field = null;
          if (key === "prompt" || key === "negative_prompt") {
            field = names.find(function (n) { return n === "text"; }) || names[0];
          } else if (key === "seed") {
            field = names.find(function (n) { return n === "seed" || n === "noise_seed"; }) || names[0];
          } else if (key === "steps") {
            field = names.find(function (n) { return n === "steps"; }) || names[0];
          } else if (key === "guidance") {
            field = names.find(function (n) { return n === "cfg" || n === "guidance"; }) || names[0];
          } else if (key === "width") {
            field = names.find(function (n) { return n === "width"; }) || names[0];
          } else if (key === "height") {
            field = names.find(function (n) { return n === "height"; }) || names[0];
          } else if (key === "input_image") {
            field = names.find(function (n) { return n === "image"; }) || names[0];
          }
          if (!field) field = names[0];
          if (!field) {
            _showToast("Node has no usable inputs", "error");
            return;
          }

          // Load profiles
          var profiles = [];
          try {
            var pr = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles");
            var pd = await pr.json();
            if (pd.status === "ok") profiles = pd.profiles || [];
          } catch (e) {
            _showToast("Failed to load profiles", "error");
            return;
          }
          if (profiles.length === 0) {
            _showToast("No comparison profiles. Save a workflow first.", "error");
            return;
          }

          var targetId = null;
          var targetName = "";
          if (profiles.length === 1) {
            targetId = profiles[0].id;
            targetName = profiles[0].name || targetId;
          } else {
            targetName = prompt("Apply mapping to which profile?\n" + profiles.map(function (p, i) { return (i + 1) + ": " + (p.name || p.id); }).join("\n"), profiles[0].name || profiles[0].id);
            if (!targetName) return;
            var match = profiles.find(function (p) { return (p.name || p.id).toLowerCase() === targetName.toLowerCase(); });
            targetId = match ? match.id : null;
            if (!targetId) {
              _showToast("Profile not found", "error");
              return;
            }
          }

          // Resolve node id in the profile's saved workflow
          var resolvedId = await _resolveProfileNode(targetId, classType, title);
          if (!resolvedId) {
            _showToast("Cannot find node '" + title + "' (" + classType + ") in this profile's saved workflow. Re-save the profile from the current canvas.", "error");
            return;
          }

          // Get current slots for the profile
          var slots = {};
          try {
            var sr = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + targetId);
            var sd = await sr.json();
            if (sd.status === "ok" && sd.profile) {
              slots = sd.profile.slots || {};
            }
          } catch (e) {
            _showToast("Failed to load profile slots", "error");
            return;
          }

          try {
            slots[key] = { node_id: resolvedId, path: ["inputs", field], field: field, class_type: classType };
            var rr = await api.fetchApi(MODAL_PREFIX + "/comparison/profiles/" + targetId + "/slots", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ slots: slots }),
            });
            var rd = await rr.json();
            if (rd.status === "ok") {
              _showToast("Mapped " + label + " \u2192 " + (title || resolvedId), "success");
            } else throw new Error(rd.message);
          } catch (err) {
            _showToast("Failed to save mapping: " + err.message, "error");
          }
        },
      };
    });

    options.push(null);
    options.push({
      content: "\u2601 Modal: Set as comparison \u25B6",
      has_submenu: true,
      submenu: {
        options: slotItems,
      },
    });

    return options;
  };
}

// ─── Reusable mount helpers for unified UI integration ─────────────────────

/**
 * Mount the Comparison Profiles tab into the given container element.
 * Used by testing-dashboard.js quick actions.
 */
window.mountComparisonProfiles = function mountComparisonProfiles(containerEl) {
  if (!containerEl) throw new Error("mountComparisonProfiles: containerEl required");
  containerEl.innerHTML = "";
  containerEl.appendChild(buildProfilesTab());
  return containerEl;
};

/**
 * Mount the Comparison Runner tab into the given container element.
 * Used by testing-dashboard.js quick actions.
 */
window.mountComparisonRunner = function mountComparisonRunner(containerEl) {
  if (!containerEl) throw new Error("mountComparisonRunner: containerEl required");
  containerEl.innerHTML = "";
  containerEl.appendChild(buildRunnerTab());
  return containerEl;
};

// ─── Open overlay-based comparison helpers ─────────────────────────────────

function _openOverlayPanel(title, builderFn) {
  const existing = document.getElementById("comfymodal-comparison-overlay");
  if (existing) {
    existing.style.display = "flex";
    return;
  }
  const overlay = document.createElement("div");
  overlay.id = "comfymodal-comparison-overlay";
  overlay.style.cssText = `
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.7); z-index: 99998;
    display: flex; align-items: center; justify-content: center;
  `;
  const modal = document.createElement("div");
  modal.style.cssText = `
    background: #1e1e2e; border: 1px solid #444; border-radius: 8px;
    width: 90%; max-width: 700px; max-height: 85vh;
    display: flex; flex-direction: column; overflow: hidden;
  `;
  const header = document.createElement("div");
  header.style.cssText = `
    display: flex; align-items: center; padding: 12px 16px;
    border-bottom: 1px solid #333; flex-shrink: 0;
  `;
  const titleEl = document.createElement("span");
  titleEl.style.cssText = "font-weight: 600; font-size: 14px; color: #ddd; flex: 1;";
  titleEl.textContent = title;
  const closeBtn = document.createElement("button");
  closeBtn.textContent = "\u2715";
  closeBtn.style.cssText = `
    background: transparent; border: 1px solid #555; color: #aaa;
    width: 28px; height: 28px; border-radius: 4px; cursor: pointer;
    font-size: 14px; display: flex; align-items: center; justify-content: center;
  `;
  header.appendChild(titleEl);
  header.appendChild(closeBtn);
  const body = document.createElement("div");
  body.style.cssText = "flex: 1; overflow-y: auto; min-height: 0;";
  modal.appendChild(header);
  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // Mount content
  builderFn(body);

  function closeOverlay() {
    overlay.style.display = "none";
    document.removeEventListener("keydown", escHandler);
  }
  const escHandler = (e) => { if (e.key === "Escape") closeOverlay(); };
  document.addEventListener("keydown", escHandler);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeOverlay(); });
  closeBtn.onclick = closeOverlay;
}

window.openComparisonProfilesOverlay = function openComparisonProfilesOverlay() {
  _openOverlayPanel("Comparison Profiles", (body) => {
    window.mountComparisonProfiles(body);
  });
};

window.openComparisonRunnerOverlay = function openComparisonRunnerOverlay() {
  _openOverlayPanel("Comparison Runner", (body) => {
    window.mountComparisonRunner(body);
  });
};

app.registerExtension({
  name: "comfyui.modal.comparison",

  async setup() {
    _initContextMenu();

    // Skip legacy sidebar tabs when unified Modal GPU tab is active.
    if (!window.__comfyModalUnifiedUI && app?.extensionManager?.registerSidebarTab) {
      // Profiles Tab
      app.extensionManager.registerSidebarTab({
        id: "modal-comparison-profiles",
        icon: "pi pi-save",
        title: "Comparison Profiles",
        tooltip: "Manage comparison profiles and slot mappings",
        type: "custom",
        render: async (el) => {
          try {
            el.style.height = "100%";
            el.innerHTML = "";
            el.appendChild(buildProfilesTab());
          } catch (e) {
            console.error("[comfyui-modal] Comparison Profiles tab render error:", e);
            el.textContent = "";
            const errDiv = document.createElement("div");
            errDiv.style.cssText = "color:#e05050;padding:20px;font-size:13px;";
            errDiv.textContent = "Error loading Comparison Profiles: " + e.message;
            el.appendChild(errDiv);
          }
        },
      });

      // Runner Tab
      app.extensionManager.registerSidebarTab({
        id: "modal-comparison-runner",
        icon: "pi pi-play",
        title: "Comparison Runner",
        tooltip: "Run multiple profiles side by side with shared inputs",
        type: "custom",
        render: async (el) => {
          try {
            el.style.height = "100%";
            el.innerHTML = "";
            el.appendChild(buildRunnerTab());
          } catch (e) {
            console.error("[comfyui-modal] Comparison Runner tab render error:", e);
            el.textContent = "";
            const errDiv = document.createElement("div");
            errDiv.style.cssText = "color:#e05050;padding:20px;font-size:13px;";
            errDiv.textContent = "Error loading Comparison Runner: " + e.message;
            el.appendChild(errDiv);
          }
        },
      });
    }
  },
});
