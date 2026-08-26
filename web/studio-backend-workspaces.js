// Modal Studio — Backend Workspaces Section (H6 re-home)
//
// Modern Backend home for Modal workspace operations, consuming the SAME
// server authority as the legacy settings panel (.modal_workspaces.json via
// /workspaces*). The browser is never the workspace authority: after every
// mutation the UI re-renders from the server's registry envelope, and a
// failed activation leaves the previous server-reported active workspace
// visibly active.
//
// Secrets policy: workspace records carry token material server-side only.
// This section renders labels/metadata, never token values (masked or raw),
// and add/edit forms hold user input in memory only until submit.

import { el, statusBadge } from "./studio-ui.js";
import { renderLoadingState } from "./studio-loading.js";
import {
  listWorkspacesRegistry,
  upsertWorkspace,
  activateWorkspace,
  requestWorkspaceSwap,
  getWorkspaceSwapStatus,
  buildSwapConfirmPayload,
  swapPhaseMessage,
  summarizeWorkspaces,
  scanManifestIssues,
  applyManifestRepairs,
  deleteManifestPlaceholder,
  inferSourceKind,
} from "./studio-backend-api.js";

const SWAP_POLL_MS = 1000;

export function renderWorkspacesSection(container, apiBase, bus) {
  const state = {
    truth: null,          // last server registry envelope (authority mirror)
    summary: null,        // safe display projection of truth
    selectedId: "",
    busy: false,
    swapJobId: null,
    swapTimer: null,
    formMode: null,       // null | "add" | "edit"
    repair: { open: false, loading: false, issues: null, message: "" },
  };

  const root = el("div", { class: "comfymodal-studio-backend-detail", "data-testid": "backend-workspaces" });

  // ── Header: truthful active identity ────────────────────────────────────
  // Initial content is the shared I3 loading primitive (role="status",
  // aria-live="polite"); renderActiveLine replaces it once server truth
  // arrives (or with the unavailable/empty line).
  const activeLine = el("div", {
    class: "comfymodal-studio-backend-active-line",
    "data-testid": "backend-workspaces-active",
    style: "font-size:12px;color:#aaa;margin-bottom:6px;",
  });
  activeLine.appendChild(renderLoadingState({
    label: "Loading workspaces\u2026",
    size: "inline",
    testid: "backend-workspaces-loading",
  }));

  // ── Workspace list ──────────────────────────────────────────────────────
  const listWrap = el("div", {
    class: "comfymodal-studio-backend-workspace-list",
    "data-testid": "backend-workspaces-list",
    style: "display:flex;flex-direction:column;gap:4px;margin-bottom:8px;",
  });

  // ── Actions ─────────────────────────────────────────────────────────────
  const actionsRow = el("div", { class: "comfymodal-studio-backend-actions", style: "flex-wrap:wrap;" });

  const activateBtn = el("button", {
    type: "button", class: "comfymodal-primary-btn", text: "Set Active",
    "data-testid": "backend-workspace-activate",
    title: "Make the selected workspace the server-resolved active workspace",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  const addBtn = el("button", {
    type: "button", text: "+ Add Workspace",
    "data-testid": "backend-workspace-add",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  const editBtn = el("button", {
    type: "button", text: "Edit Workspace",
    "data-testid": "backend-workspace-edit",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  const swapBtn = el("button", {
    type: "button", class: "comfymodal-primary-btn", text: "Swap Workspace",
    "data-testid": "backend-workspace-swap",
    title: "Switch to the selected workspace: sync models/nodes, then deploy",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  const repairBtn = el("button", {
    type: "button", text: "Manifest Repair",
    "data-testid": "backend-manifest-repair-toggle",
    title: "Scan and repair model-manifest entries that block workspace swaps",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  actionsRow.appendChild(activateBtn);
  actionsRow.appendChild(addBtn);
  actionsRow.appendChild(editBtn);
  actionsRow.appendChild(swapBtn);
  actionsRow.appendChild(repairBtn);

  // ── Inline form panel (add/edit) ────────────────────────────────────────
  const formPanel = el("div", {
    "data-testid": "backend-workspace-form",
    style: "display:none;border:1px solid #2a2a2a;border-radius:3px;padding:12px;margin-bottom:8px;max-width:420px;",
  });

  // ── Swap review / confirm panel ─────────────────────────────────────────
  const swapPanel = el("div", {
    "data-testid": "backend-workspace-swap-panel",
    style: "display:none;border:1px solid #2a2a2a;border-radius:3px;padding:12px;margin-bottom:8px;",
  });

  // ── Progress / result line ──────────────────────────────────────────────
  const progressLine = el("div", {
    "data-testid": "backend-workspaces-progress",
    style: "font-size:11px;color:#aaa;min-height:16px;margin:4px 0 8px;",
  });

  function setProgress(text, color) {
    while (progressLine.firstChild) progressLine.removeChild(progressLine.firstChild);
    if (!text) return;
    progressLine.appendChild(el("span", { text, style: `color:${color || "#aaa"};` }));
  }

  // ── Manifest repair panel ───────────────────────────────────────────────
  const repairPanel = el("div", {
    "data-testid": "backend-manifest-repair",
    style: "display:none;border:1px solid #2a2a2a;border-radius:3px;padding:12px;margin-top:8px;",
  });

  root.appendChild(activeLine);
  root.appendChild(listWrap);
  root.appendChild(actionsRow);
  root.appendChild(formPanel);
  root.appendChild(swapPanel);
  root.appendChild(progressLine);
  root.appendChild(repairPanel);

  // ── Rendering from server truth ─────────────────────────────────────────

  function renderActiveLine() {
    const s = state.summary;
    if (!state.truth) {
      activeLine.textContent = "Workspace registry unavailable.";
      return;
    }
    if (!s || !s.rows.length) {
      activeLine.textContent = "No saved Modal workspaces yet.";
      return;
    }
    activeLine.textContent = "";
    activeLine.appendChild(el("span", { text: "Active workspace: " }));
    activeLine.appendChild(el("span", {
      text: s.activeLabel || "none",
      style: "color:#7ed321;font-weight:600;",
      "data-testid": "backend-workspaces-active-label",
    }));
    activeLine.appendChild(document.createTextNode(" (server-resolved at dispatch)"));
  }

  function renderList() {
    while (listWrap.firstChild) listWrap.removeChild(listWrap.firstChild);
    const s = state.summary;
    if (!state.truth) return;
    if (!s.rows.length) return;
    s.rows.forEach((row) => {
      const card = el("div", {
        class: "comfymodal-studio-backend-card" + (row.id === state.selectedId ? " active" : ""),
        "data-testid": "backend-workspace-card",
        "data-workspace-id": row.id,
        role: "button",
        tabindex: "0",
      }, [
        el("h4", { text: row.label }),
        el("p", { text: row.isActive ? "Active workspace" : `Idle \u00b7 last deploy: ${row.lastDeployStatus}` }),
      ]);
      if (row.isActive) {
        card.appendChild(statusBadge("ACTIVE", "ok"));
      }
      card.addEventListener("click", () => {
        state.selectedId = row.id;
        syncActionButtons();
        renderList();
      });
      listWrap.appendChild(card);
    });
  }

  function syncActionButtons() {
    const s = state.summary;
    const hasSelection = !!state.selectedId;
    const selectionIsActive = !!(s && state.selectedId && state.selectedId === s.activeId);
    activateBtn.disabled = state.busy || !hasSelection || selectionIsActive;
    editBtn.disabled = state.busy || !hasSelection;
    swapBtn.disabled = state.busy || !hasSelection || selectionIsActive;
    addBtn.disabled = state.busy;
    repairBtn.disabled = state.busy;
  }

  function renderFromTruth() {
    state.summary = summarizeWorkspaces(state.truth);
    renderActiveLine();
    renderList();
    syncActionButtons();
  }

  async function refreshTruth(envelope) {
    state.truth = envelope || (await listWorkspacesRegistry(apiBase));
    if (state.truth && state.truth.status === "error") state.truth = null;
    if (state.truth && !state.selectedId) {
      const s = summarizeWorkspaces(state.truth);
      state.selectedId = s.activeId || (s.rows[0] ? s.rows[0].id : "");
    }
    renderFromTruth();
  }

  // ── Mutations (server-authoritative) ────────────────────────────────────

  async function activateSelected() {
    if (activateBtn.disabled) return;
    const targetId = state.selectedId;
    const previousTruth = state.truth;
    setBusy(true);
    setProgress("Activating workspace\u2026", "#888");
    let resp = null;
    try {
      resp = await activateWorkspace(apiBase, targetId);
    } catch {
      resp = null;
    }
    if (resp && resp.status === "ok" && Array.isArray(resp.workspaces)) {
      await refreshTruth(resp);
      setProgress(`Active workspace is now ${summarizeWorkspaces(resp).activeLabel || targetId}.`, "#7ed321");
      emitChanged();
    } else {
      // Failure: previous server truth stays rendered and visibly active.
      state.truth = previousTruth;
      renderFromTruth();
      const msg = (resp && (resp.message || resp.error)) || "Activation failed.";
      setProgress(`Activation failed: ${msg}`, "#e05050");
    }
    setBusy(false);
  }

  function setBusy(busy) {
    state.busy = busy;
    syncActionButtons();
  }

  function emitChanged() {
    if (bus && typeof bus.emit === "function") bus.emit("workspace-changed");
  }

  // ── Add / Edit form ─────────────────────────────────────────────────────

  function closeForm() {
    state.formMode = null;
    while (formPanel.firstChild) formPanel.removeChild(formPanel.firstChild);
    formPanel.style.display = "none";
  }

  function openForm(mode) {
    const editing = mode === "edit";
    const selected = (state.summary && state.summary.rows.find((r) => r.id === state.selectedId)) || null;
    if (editing && !selected) return;
    state.formMode = mode;
    while (formPanel.firstChild) formPanel.removeChild(formPanel.firstChild);
    formPanel.style.display = "block";

    const title = el("div", { text: editing ? "Edit Modal Workspace" : "Add Modal Workspace", style: "font-weight:600;font-size:12px;margin-bottom:8px;" });
    const labelField = field("Label", "text", editing ? selected.label : "", "Workspace label (e.g. Studio A)");
    const idField = field("Token ID", "text", "", editing ? "ak-\u2026 \u2014 leave blank to keep current" : "Token ID (ak-...)");
    const secretField = field("Token Secret", "password", "", editing ? "as-\u2026 \u2014 leave blank to keep current" : "Token Secret (as-...)");
    const errLine = el("div", { "data-testid": "backend-workspace-form-error", style: "font-size:11px;color:#e05050;min-height:14px;", text: "" });
    const saveBtn = el("button", {
      type: "button", class: "comfymodal-primary-btn", text: "Save Workspace",
      "data-testid": "backend-workspace-save",
      style: "width:auto;padding:5px 12px;font-size:11px;",
    });
    const cancelBtn = el("button", {
      type: "button", text: "Cancel", "data-testid": "backend-workspace-cancel",
      style: "width:auto;padding:5px 12px;font-size:11px;",
    });
    const btnRow = el("div", { style: "display:flex;gap:6px;margin-top:8px;" }, [saveBtn, cancelBtn]);

    formPanel.appendChild(title);
    formPanel.appendChild(labelField.wrap);
    formPanel.appendChild(idField.wrap);
    formPanel.appendChild(secretField.wrap);
    formPanel.appendChild(errLine);
    formPanel.appendChild(btnRow);

    cancelBtn.addEventListener("click", closeForm);
    saveBtn.addEventListener("click", async () => {
      const label = labelField.input.value.trim();
      const token_id = idField.input.value.trim();
      const token_secret = secretField.input.value.trim();
      errLine.textContent = "";
      if (!label) { errLine.textContent = "Workspace label required."; return; }
      if (!editing && (!token_id || !token_secret)) { errLine.textContent = "Token ID and Token Secret are required."; return; }
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving\u2026";
      const payload = editing
        ? { workspace_id: selected.id, label, token_id, token_secret, set_active: false }
        : { label, token_id, token_secret, set_active: false };
      let resp = null;
      try {
        resp = await upsertWorkspace(apiBase, payload);
      } catch { resp = null; }
      saveBtn.disabled = false;
      saveBtn.textContent = "Save Workspace";
      if (resp && resp.status === "ok" && Array.isArray(resp.workspaces)) {
        closeForm();
        await refreshTruth(resp);
        setProgress(editing ? "Workspace updated." : "Workspace added.", "#7ed321");
        emitChanged();
      } else {
        errLine.textContent = (resp && (resp.message || resp.error)) || "Save failed.";
      }
    });
  }

  function field(labelText, type, value, placeholder) {
    const input = el("input", { type, value, placeholder, style: "width:100%;box-sizing:border-box;background:#0a0a0a;border:1px solid #2a2a2a;color:#d0d0d0;padding:5px 8px;font-size:12px;border-radius:2px;" });
    const wrap = el("div", { class: "comfymodal-studio-backend-field" }, [
      el("label", { text: labelText }),
      input,
    ]);
    return { wrap, input };
  }

  // ── Swap flow (exact legacy route contract) ─────────────────────────────

  function closeSwapPanel() {
    while (swapPanel.firstChild) swapPanel.removeChild(swapPanel.firstChild);
    swapPanel.style.display = "none";
  }

  function beginSwapPolling(swapId) {
    state.swapJobId = swapId;
    setProgress("Swap started\u2026", "#888");
    pollSwapJob();
  }

  async function pollSwapJob() {
    if (!state.swapJobId) return;
    let data = null;
    try {
      data = await getWorkspaceSwapStatus(apiBase, state.swapJobId);
    } catch { data = null; }
    if (!state.swapJobId) return;
    if (!data || data.status === "not_found") {
      finishSwap(`Swap status unavailable.`, "#e05050");
      return;
    }
    if (data.status === "running") {
      setProgress(swapPhaseMessage(data) || "Working\u2026", "#f5a623");
      state.swapTimer = setTimeout(pollSwapJob, SWAP_POLL_MS);
      return;
    }
    if (data.status === "ok") {
      finishSwap(`Done \u2014 ${data.workspace_label || "workspace"}: ${data.download_summary || `${data.installed_model_count || 0} installed, ${data.skipped_model_count || 0} skipped`}. Deploy started.`, "#7ed321");
      return;
    }
    if (data.status === "repair_required") {
      finishSwap(`Swap blocked: ${data.message || "manifest repair required"}`, "#e07070");
      openRepair();
      return;
    }
    finishSwap(data.message || data.error || data.deploy_message || data.sync_message || data.download_message || "Workspace swap failed", "#e05050");
  }

  function finishSwap(message, color) {
    state.swapJobId = null;
    setBusy(false);
    closeSwapPanel();
    setProgress(message, color);
    refreshTruth();
    emitChanged();
  }

  async function startSwap(extraPayload) {
    const targetId = state.selectedId;
    let data = null;
    try {
      data = await requestWorkspaceSwap(apiBase, Object.assign({ workspace_id: targetId }, extraPayload || {}));
    } catch { data = null; }
    if (!data) {
      setBusy(false);
      setProgress("Workspace swap failed.", "#e05050");
      return;
    }
    if (data.status === "busy") {
      setBusy(false);
      setProgress(data.message || "Deploy already running \u2014 try again later.", "#888");
      return;
    }
    if (data.status === "error") {
      setBusy(false);
      setProgress(data.message || "Workspace swap failed.", "#e05050");
      return;
    }
    if (data.status === "confirm_required") {
      showSwapConfirm(targetId);
      return;
    }
    if (data.status === "repair_required") {
      setBusy(false);
      setProgress(`Swap blocked: ${data.message || "manifest repair required"}`, "#e07070");
      openRepair();
      return;
    }
    if (data.status === "review_required") {
      showSwapReview(targetId, data);
      return;
    }
    if (data.status === "started" && data.swap_id) {
      beginSwapPolling(data.swap_id);
      return;
    }
    setBusy(false);
    setProgress(data.message || "Unexpected swap response.", "#e05050");
  }

  function showSwapConfirm(targetId) {
    while (swapPanel.firstChild) swapPanel.removeChild(swapPanel.firstChild);
    swapPanel.style.display = "block";
    const msg = el("div", { text: "A prompt is still running. Switch workspaces anyway?", style: "font-size:12px;color:#ccc;margin-bottom:8px;" });
    const yes = el("button", { type: "button", class: "comfymodal-primary-btn", text: "Interrupt and Switch", "data-testid": "backend-swap-confirm-yes", style: "width:auto;padding:5px 12px;font-size:11px;" });
    const no = el("button", { type: "button", text: "Cancel", "data-testid": "backend-swap-confirm-no", style: "width:auto;padding:5px 12px;font-size:11px;" });
    yes.addEventListener("click", () => {
      closeSwapPanel();
      startSwap({ confirm_prompt_interrupt: true });
    });
    no.addEventListener("click", () => {
      setBusy(false);
      closeSwapPanel();
      setProgress("Swap cancelled.", "#888");
    });
    swapPanel.appendChild(msg);
    swapPanel.appendChild(el("div", { style: "display:flex;gap:6px;" }, [yes, no]));
  }

  function showSwapReview(targetId, data) {
    while (swapPanel.firstChild) swapPanel.removeChild(swapPanel.firstChild);
    swapPanel.style.display = "block";
    const toInstall = data.to_install || [];
    const installCount = data.install_count || 0;
    const presentCount = data.present_count || 0;
    const removeCount = (data.to_remove || []).length;

    swapPanel.appendChild(el("div", { style: "font-weight:600;font-size:12px;margin-bottom:6px;" }, [
      el("span", { text: "Workspace: " }),
      el("span", { text: data.workspace_label || targetId, style: "color:#6a9fd8;" }),
    ]));

    if (installCount === 0) {
      swapPanel.appendChild(el("div", {
        text: "All manifest models are already in the target workspace. Custom nodes will be synced and a deploy will run.",
        style: "font-size:11px;color:#aaa;margin-bottom:8px;",
      }));
    } else {
      swapPanel.appendChild(el("div", { text: "Select models to download to the target workspace:", style: "font-size:11px;color:#f5a623;margin-bottom:6px;font-weight:600;" }));
    }

    const checks = [];
    const checkList = el("div", { "data-testid": "backend-swap-review-list", style: "max-height:200px;overflow-y:auto;display:flex;flex-direction:column;gap:2px;margin-bottom:8px;" });
    toInstall.forEach((m) => {
      const key = `${m.save_path || m.folder || ""}/${m.filename || ""}`;
      const cb = el("input", { type: "checkbox" });
      cb.checked = true;
      checks.push({ key, cb });
      checkList.appendChild(el("label", { style: "display:flex;align-items:center;gap:6px;font-size:11px;color:#ccc;" }, [
        cb,
        el("span", { text: `${m.filename || ""} (${m.folder || m.save_path || "?"})` }),
      ]));
    });
    if (toInstall.length) swapPanel.appendChild(checkList);

    if (removeCount) {
      swapPanel.appendChild(el("div", { text: `${removeCount} manifest model(s) marked for removal from the current workspace.`, style: "font-size:11px;color:#888;margin-bottom:8px;" }));
    }
    swapPanel.appendChild(el("div", { text: `${presentCount} already present \u00b7 ${installCount} selectable.`, style: "font-size:11px;color:#888;margin-bottom:8px;" }));

    const goBtn = el("button", { type: "button", class: "comfymodal-primary-btn", text: "Start Swap", "data-testid": "backend-swap-review-go", style: "width:auto;padding:5px 12px;font-size:11px;" });
    const cancelBtn = el("button", { type: "button", text: "Cancel", "data-testid": "backend-swap-review-cancel", style: "width:auto;padding:5px 12px;font-size:11px;" });
    goBtn.addEventListener("click", () => {
      const selectedKeys = checks.filter((c) => c.cb.checked).map((c) => c.key);
      closeSwapPanel();
      startSwap(buildSwapConfirmPayload(targetId, selectedKeys));
    });
    cancelBtn.addEventListener("click", () => {
      setBusy(false);
      closeSwapPanel();
      setProgress("Swap cancelled.", "#888");
    });
    swapPanel.appendChild(el("div", { style: "display:flex;gap:6px;" }, [goBtn, cancelBtn]));
  }

  function onSwapClicked() {
    if (swapBtn.disabled) return;
    setBusy(true);
    setProgress("Scanning workspace and manifest\u2026", "#888");
    startSwap();
  }

  // ── Manifest repair ─────────────────────────────────────────────────────

  function openRepair() {
    state.repair.open = true;
    repairPanel.style.display = "block";
    renderRepair();
    runRepairScan();
  }

  function closeRepair() {
    state.repair.open = false;
    while (repairPanel.firstChild) repairPanel.removeChild(repairPanel.firstChild);
    repairPanel.style.display = "none";
  }

  function renderRepair() {
    while (repairPanel.firstChild) repairPanel.removeChild(repairPanel.firstChild);
    repairPanel.appendChild(el("div", { style: "font-weight:600;font-size:12px;margin-bottom:6px;", text: "Model Manifest Repair" }));
    repairPanel.appendChild(el("div", {
      text: "Repairs manifest entries that block workspace swaps. Deployment bootstrap concern \u2014 model browsing/install lives in Workflows \u2192 Model Library.",
      style: "font-size:11px;color:#888;margin-bottom:8px;",
    }));
    const body = el("div", { "data-testid": "backend-manifest-repair-body" });
    repairPanel.appendChild(body);
    if (state.repair.loading) {
      body.appendChild(el("div", { text: "Scanning manifest\u2026", style: "font-size:11px;color:#888;" }));
      return;
    }
    if (state.repair.message) {
      body.appendChild(el("div", { "data-testid": "backend-manifest-repair-message", text: state.repair.message, style: "font-size:11px;color:#aaa;margin-bottom:6px;" }));
    }
    const issues = state.repair.issues || [];
    if (!issues.length) return;

    const rows = [];
    const table = el("table", { style: "width:100%;border-collapse:collapse;font-size:11px;margin-bottom:8px;" });
    const thead = el("thead", {}, [el("tr", {}, ["Folder", "Filename", "URL", "Source", "Remove", ""].map((t) =>
      el("th", { text: t, style: "text-align:left;padding:4px;border-bottom:1px solid #2a2a2a;" })))]);
    const tbody = el("tbody");
    issues.forEach((issue) => {
      const urlInput = el("input", {
        type: "text", value: issue.url || "", placeholder: "https://huggingface.co/...",
        style: "width:100%;box-sizing:border-box;background:#0a0a0a;border:1px solid #2a2a2a;color:#d0d0d0;padding:3px 6px;font-size:11px;border-radius:2px;",
      });
      const sourceSelect = el("select", { style: "background:#0a0a0a;border:1px solid #2a2a2a;color:#d0d0d0;padding:3px;font-size:11px;border-radius:2px;" });
      ["unknown", "huggingface", "civitai", "direct"].forEach((kind) => {
        const opt = el("option", { value: kind, text: kind });
        if ((issue.source_kind || "unknown") === kind) opt.selected = true;
        sourceSelect.appendChild(opt);
      });
      urlInput.addEventListener("input", () => {
        const detected = inferSourceKind(urlInput.value);
        if (detected !== "unknown") sourceSelect.value = detected;
      });
      const removeCb = el("input", { type: "checkbox" });
      removeCb.checked = !!issue.remove_on_swap;
      removeCb.title = "Remove from workspace on next swap";
      const delBtn = el("button", { type: "button", text: "Delete", style: "width:auto;padding:2px 8px;font-size:10px;" });
      delBtn.addEventListener("click", async () => {
        delBtn.disabled = true;
        let resp = null;
        try {
          resp = await deleteManifestPlaceholder(apiBase, issue.folder, issue.filename);
        } catch { resp = null; }
        if (resp && resp.removed) {
          state.repair.issues = issues.filter((i) => !(i.folder === issue.folder && i.filename === issue.filename));
          renderRepair();
        } else {
          delBtn.disabled = false;
          state.repair.message = (resp && resp.message) || "Placeholder could not be deleted.";
          renderRepair();
        }
      });
      const tr = el("tr", {}, [
        el("td", { text: issue.folder || "", style: "padding:4px;white-space:nowrap;" }),
        el("td", { text: issue.filename || "", style: "padding:4px;word-break:break-all;" }),
        el("td", { style: "padding:4px;" }, [urlInput]),
        el("td", { style: "padding:4px;" }, [sourceSelect]),
        el("td", { style: "padding:4px;text-align:center;" }, [removeCb]),
        el("td", { style: "padding:4px;" }, [delBtn]),
      ]);
      tbody.appendChild(tr);
      rows.push({ issue, urlInput, sourceSelect, removeCb });
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    body.appendChild(table);

    const saveAll = el("button", { type: "button", class: "comfymodal-primary-btn", text: "Save All Valid", "data-testid": "backend-manifest-repair-apply", style: "width:auto;padding:5px 12px;font-size:11px;" });
    const skipAll = el("button", { type: "button", text: "Skip All", "data-testid": "backend-manifest-repair-skip", style: "width:auto;padding:5px 12px;font-size:11px;" });
    const closeB = el("button", { type: "button", text: "Close", style: "width:auto;padding:5px 12px;font-size:11px;" });
    saveAll.addEventListener("click", () => applyRepairs(rows.filter((r) => r.urlInput.value.trim() || r.removeCb.checked).map((r) => ({
      folder: r.issue.folder,
      filename: r.issue.filename,
      url: r.urlInput.value.trim(),
      source_kind: r.sourceSelect.value,
      ...(r.removeCb.checked ? { remove: true } : {}),
    }))));
    skipAll.addEventListener("click", () => applyRepairs(rows.map((r) => ({ folder: r.issue.folder, filename: r.issue.filename, skip: true }))));
    closeB.addEventListener("click", closeRepair);
    body.appendChild(el("div", { style: "display:flex;gap:6px;" }, [saveAll, skipAll, closeB]));
  }

  async function applyRepairs(updates) {
    let resp = null;
    try {
      resp = await applyManifestRepairs(apiBase, updates);
    } catch { resp = null; }
    if (resp && resp.status === "ok") {
      state.repair.issues = resp.issues || [];
      state.repair.message = state.repair.issues.length
        ? "Manifest still has unresolved rows."
        : "Manifest repair saved.";
    } else {
      state.repair.message = (resp && (resp.message || resp.error)) || "Manifest repair failed.";
    }
    renderRepair();
  }

  async function runRepairScan() {
    state.repair.loading = true;
    state.repair.message = "";
    renderRepair();
    let resp = null;
    try {
      resp = await scanManifestIssues(apiBase);
    } catch { resp = null; }
    state.repair.loading = false;
    if (resp && resp.status === "ok") {
      state.repair.issues = resp.issues || [];
      if (!state.repair.issues.length) {
        state.repair.message = "No manifest issues found.";
      }
    } else {
      state.repair.issues = [];
      state.repair.message = (resp && (resp.message || resp.error)) || "Manifest scan failed.";
    }
    if (state.repair.open) renderRepair();
  }

  // ── Wiring ──────────────────────────────────────────────────────────────

  activateBtn.addEventListener("click", activateSelected);
  addBtn.addEventListener("click", () => openForm("add"));
  editBtn.addEventListener("click", () => openForm("edit"));
  swapBtn.addEventListener("click", onSwapClicked);
  repairBtn.addEventListener("click", () => {
    if (state.repair.open) closeRepair(); else openRepair();
  });

  refreshTruth();

  container.appendChild(root);
  return root;
}
