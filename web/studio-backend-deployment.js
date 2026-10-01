// Modal Studio — Backend Deployment Section (H6 re-home)
//
// Modern Backend home for deployment controls, consuming the SAME routes and
// semantics as the legacy settings panel: POST /deploy (trigger),
// GET /deploy/status (server-reported truth), GET /deploy/log (diagnostics).
//
// Safety contract:
//  - Deploy / Redeploy+Restart run ONLY on explicit user action.
//  - Rapid clicks are deduped; in-flight state is visible; failures are
//    bounded messages. No deploy on mount, from polling, or on workspace
//    change (workspace change only re-READS status).
//  - Status is displayed verbatim from the server; readiness is never
//    inferred from HTTP success or cached browser data.

import { el, statusBadge } from "./studio-ui.js";
import {
  getDeployStatus,
  triggerDeploy,
  getCustomNodeSyncStatus,
  triggerPushPlugins,
  triggerRebuildDependencies,
  getDeployLog,
  normalizeDeployStatus,
  isDeployInFlight,
  tailLines,
} from "./studio-backend-api.js";

const STATUS_POLL_MS = 3000;
const LOG_POLL_MS = 2000;
const LOG_TAIL_LINES = 120;
const REDEPLOY_POLL_TIMEOUT_MS = 10 * 60 * 1000;
const RESTART_POLL_TIMEOUT_MS = 600 * 1000;

export function customNodeSyncMessages(data) {
  const validInventoryStates = ["match", "differs", "ambiguous", "unknown"];
  const validPayloadStates = ["exact", "differs", "unknown"];
  const validDependencyStates = ["changed", "same", "unknown"];
  if (!data || typeof data !== "object"
    || data.status === "error"
    || validInventoryStates.indexOf(data.inventory_state) === -1
    || validPayloadStates.indexOf(data.payload_state) === -1
    || validDependencyStates.indexOf(data.dependencies_state) === -1) {
    return [{ id: "unavailable", kind: "neutral", label: "UNKNOWN", text: "Custom-node sync status unavailable — refresh status to try again." }];
  }

  const messages = [];
  const localOnly = Array.isArray(data.local_only) ? data.local_only : [];
  const publishedOnly = Array.isArray(data.published_only) ? data.published_only : [];
  const dependenciesChanged = Array.isArray(data.dependencies_changed) ? data.dependencies_changed : [];
  const duplicates = Array.isArray(data.duplicates) ? data.duplicates : [];
  const unknownIdentity = Array.isArray(data.unknown_identity) ? data.unknown_identity : [];
  const inventoryUnknown = data.inventory_state === "unknown";
  const inventoryAmbiguous = data.inventory_state === "ambiguous";
  const payloadUnknown = data.payload_state === "unknown";

  if (inventoryUnknown || payloadUnknown) {
    messages.push({
      id: "unknown",
      kind: "neutral",
      label: "UNKNOWN",
      text: "Custom-node sync state is unknown — refresh status to try again.",
    });
  } else {
    if (data.inventory_state === "differs" && localOnly.length) {
      messages.push({
        id: "local-only",
        kind: "warn",
        label: "PUBLISH",
        text: `${localOnly.length} plugin${localOnly.length === 1 ? " is" : "s are"} installed locally but not yet published — use Push plugins (FAST).`,
      });
    } else if (data.inventory_state === "differs" && publishedOnly.length) {
      messages.push({
        id: "published-only",
        kind: "warn",
        label: "INVENTORY",
        text: `${publishedOnly.length} published plugin${publishedOnly.length === 1 ? " is" : "s are"} not installed locally — refresh status to inspect.`,
      });
    } else if (data.inventory_state === "differs") {
      messages.push({
        id: "inventory",
        kind: "warn",
        label: "INVENTORY",
        text: "Installed plugin inventory differs from the published inventory — refresh status to inspect.",
      });
    }
    if (data.payload_state === "differs") {
      messages.push({
        id: "payload",
        kind: "warn",
        label: "PUBLISH",
        text: "Published plugin contents differ from local — use Push plugins (FAST).",
      });
    }
  }

  if (data.dependencies_state === "changed" || dependenciesChanged.length) {
    const count = dependenciesChanged.length;
    messages.push({
      id: "dependencies",
      kind: "warn",
      label: "REBUILD",
      text: count
        ? `${count} plugin${count === 1 ? " has" : "s have"} changed dependencies — use Rebuild dependencies (SLOW).`
        : "One or more plugins have changed dependencies — use Rebuild dependencies (SLOW).",
    });
  } else if (data.dependencies_state === "unknown") {
    messages.push({
      id: "dependencies-unknown",
      kind: "neutral",
      label: "UNKNOWN",
      text: "Custom-node dependency sync state is unknown — refresh status to try again.",
    });
  }

  const identityCount = duplicates.length + unknownIdentity.length;
  if (identityCount || inventoryAmbiguous) {
    messages.push({
      id: "identity",
      kind: "neutral",
      label: "NOTE",
      text: identityCount
        ? `Plugin identity is ambiguous for ${identityCount} item${identityCount === 1 ? "" : "s"} — refresh status to inspect.`
        : "Plugin identity is ambiguous — refresh status to inspect.",
    });
  }

  if (!messages.length) {
    messages.push({ id: "clear", kind: "ok", label: "OK", text: "Custom-node sync is current." });
  }
  return messages;
}

export function renderDeploymentSection(container, apiBase, bus) {
  const state = {
    status: null,          // normalized server truth
    deploying: false,      // user-visible in-flight flag for THIS page's actions
    pollTimer: null,
    logTimer: null,
    logVisible: false,
    redeployBusy: false,
    pushBusy: false,
    rebuildBusy: false,
    customNodeSync: null,
    customNodeSyncLoaded: false,
  };

  const root = el("div", { class: "comfymodal-studio-backend-detail", "data-testid": "backend-deployment" });

  // ── Status card ─────────────────────────────────────────────────────────
  const statusCard = el("div", {
    class: "comfymodal-studio-backend-detail-card",
    "data-testid": "backend-deploy-status",
    style: "margin-bottom:8px;",
  });

  // ── Actions ─────────────────────────────────────────────────────────────
  const deployBtn = el("button", {
    type: "button", class: "comfymodal-primary-btn", text: "Deploy",
    "data-testid": "backend-deploy-trigger",
    title: "Deploy or re-deploy comfyapp.py to Modal",
    style: "width:auto;padding:5px 14px;font-size:11px;",
  });
  const restartBtn = el("button", {
    type: "button", class: "comfymodal-primary-btn", text: "Redeploy and Restart",
    "data-testid": "backend-deploy-restart",
    title: "Redeploy to Modal, restart ComfyUI, and refresh",
    style: "width:auto;padding:5px 14px;font-size:11px;background:#5a3fcc;border-color:#6a4fe0;",
  });
  const refreshBtn = el("button", {
    type: "button", text: "Refresh Status",
    "data-testid": "backend-deploy-refresh",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  const pushPluginsBtn = el("button", {
    type: "button", text: "Push plugins (FAST)",
    "data-testid": "backend-custom-node-push",
    title: "Quickly publish the installed custom nodes without rebuilding dependencies",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  const rebuildDependenciesBtn = el("button", {
    type: "button", text: "Rebuild dependencies (SLOW)",
    "data-testid": "backend-custom-node-rebuild-dependencies",
    title: "Rebuild custom-node dependencies; this takes considerably longer than pushing plugins",
    style: "width:auto;padding:5px 12px;font-size:11px;background:#5a3a18;border-color:#8a5a22;color:#f0c36d;",
  });
  const logToggleBtn = el("button", {
    type: "button", text: "Show Deploy Log",
    "data-testid": "backend-deploy-log-toggle",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  const actionsRow = el("div", { class: "comfymodal-studio-backend-actions", style: "flex-wrap:wrap;margin-bottom:8px;" }, [
    deployBtn, restartBtn, refreshBtn, pushPluginsBtn, rebuildDependenciesBtn, logToggleBtn,
  ]);

  const customNodeSyncCard = el("div", {
    "data-testid": "backend-custom-node-sync",
    style: "display:none;border:1px solid #2a2a2a;border-radius:3px;padding:7px 9px;margin-bottom:8px;",
  });

  // ── Log viewer (bounded; explicit open) ─────────────────────────────────
  const logPanel = el("div", {
    "data-testid": "backend-deploy-log",
    style: "display:none;border:1px solid #2a2a2a;border-radius:3px;padding:10px;margin-bottom:8px;",
  });
  const logPre = el("pre", {
    "data-testid": "backend-deploy-log-text",
    style: "margin:6px 0 0;padding:8px;background:#111;color:#aaa;font-size:11px;line-height:1.45;max-height:220px;overflow-y:auto;border-radius:3px;border:1px solid #333;white-space:pre-wrap;word-break:break-all;",
    text: "",
  });
  const logRefreshBtn = el("button", { type: "button", text: "Refresh Log", "data-testid": "backend-deploy-log-refresh", style: "width:auto;padding:3px 10px;font-size:10px;" });

  root.appendChild(statusCard);
  root.appendChild(customNodeSyncCard);
  root.appendChild(actionsRow);
  root.appendChild(logPanel);
  root.appendChild(el("div", {
    text: "Deployment identity and readiness are server-reported truth.",
    style: "font-size:10px;color:#555;",
  }));

  function renderStatus() {
    while (statusCard.firstChild) statusCard.removeChild(statusCard.firstChild);
    if (!state.status || !state.status.available) {
      statusCard.appendChild(el("div", {
        "data-testid": "backend-deploy-status-unavailable",
        text: "Deploy status unavailable.",
        style: "font-size:12px;color:#888;",
      }));
      return;
    }
    const s = state.status;
    const kind = s.state === "ready" ? "ok"
      : s.state === "error" ? "error"
      : isDeployInFlight(s.state) ? "warn"
      : "neutral";
    const head = el("div", { style: "display:flex;align-items:center;gap:8px;margin-bottom:4px;" }, [
      statusBadge(s.state.toUpperCase(), kind),
      el("span", { "data-testid": "backend-deploy-state", text: s.state, style: "font-size:11px;color:#888;" }),
    ]);
    statusCard.appendChild(head);
    if (s.message) {
      statusCard.appendChild(el("div", {
        "data-testid": "backend-deploy-message",
        text: s.message,
        style: "font-size:12px;color:#ccc;",
      }));
    }
    const metaBits = [];
    if (s.comfyappVersion) metaBits.push(`version: ${s.comfyappVersion}`);
    if (s.deployedAt) metaBits.push(`deployed: ${s.deployedAt}`);
    if (metaBits.length) {
      statusCard.appendChild(el("div", { text: metaBits.join(" \u00b7 "), style: "font-size:11px;color:#666;margin-top:4px;" }));
    }
  }

  function renderCustomNodeSync() {
    while (customNodeSyncCard.firstChild) customNodeSyncCard.removeChild(customNodeSyncCard.firstChild);
    if (!state.customNodeSyncLoaded) {
      customNodeSyncCard.style.display = "none";
      return;
    }
    customNodeSyncCard.style.display = "block";
    customNodeSyncMessages(state.customNodeSync).forEach((message) => {
      customNodeSyncCard.appendChild(el("div", {
        "data-testid": `backend-custom-node-sync-${message.id}`,
        style: "display:flex;align-items:center;gap:7px;font-size:11px;color:#aaa;line-height:1.45;",
      }, [
        statusBadge(message.label, message.kind),
        el("span", { text: message.text }),
      ]));
    });
  }

  function syncButtons() {
    const busy = state.deploying || state.redeployBusy;
    deployBtn.disabled = busy;
    restartBtn.disabled = busy;
    const syncBusy = state.pushBusy || state.rebuildBusy;
    pushPluginsBtn.disabled = syncBusy;
    rebuildDependenciesBtn.disabled = syncBusy;
    pushPluginsBtn.textContent = state.pushBusy ? "Pushing plugins…" : "Push plugins (FAST)";
    rebuildDependenciesBtn.textContent = state.rebuildBusy ? "Rebuilding dependencies…" : "Rebuild dependencies (SLOW)";
    deployBtn.textContent = state.deploying ? "Deploying\u2026" : "Deploy";
  }

  async function readStatus() {
    let data = null;
    try { data = await getDeployStatus(apiBase); } catch { data = null; }
    state.status = normalizeDeployStatus(data);
    renderStatus();
    return state.status;
  }

  async function readCustomNodeSyncStatus() {
    let data = null;
    try { data = await getCustomNodeSyncStatus(apiBase); } catch { data = null; }
    state.customNodeSync = data && data.status === "ok" ? data : null;
    state.customNodeSyncLoaded = true;
    renderCustomNodeSync();
    return state.customNodeSync;
  }

  // Status polling exists ONLY after a user-initiated deploy (legacy parity).
  function armStatusPoll() {
    if (state.pollTimer) return;
    state.pollTimer = setTimeout(pollStatusTick, STATUS_POLL_MS);
  }

  async function pollStatusTick() {
    state.pollTimer = null;
    const s = await readStatus();
    if (state.logVisible && isDeployInFlight(s.state)) {
      refreshLog();
    }
    if (isDeployInFlight(s.state)) {
      armStatusPoll();
      return;
    }
    state.deploying = false;
    syncButtons();
    emitDeployState();
  }

  function emitDeployState() {
    if (bus && typeof bus.emit === "function") bus.emit("deploy-status-changed");
  }

  async function onDeployClicked() {
    if (deployBtn.disabled) return;           // dedupe rapid clicks
    state.deploying = true;
    syncButtons();
    let resp = null;
    try { resp = await triggerDeploy(apiBase); } catch { resp = null; }
    if (!resp) {
      state.deploying = false;
      syncButtons();
      appendBoundedResult("Deploy request failed.", "#e05050");
      return;
    }
    if (resp.status === "started" || resp.status === "already_deploying") {
      await readStatus();
      armStatusPoll();
      emitDeployState();
      appendBoundedResult(resp.status === "started" ? "Deploy started." : "Deploy already running \u2014 showing live status.", "#7ed321");
      return;
    }
    state.deploying = false;
    syncButtons();
    appendBoundedResult(resp.message || resp.error || "Deploy could not be started.", "#e05050");
  }

  // Bounded result line under the action row (re-created per event).
  let resultLine = null;
  function appendBoundedResult(text, color) {
    if (resultLine && resultLine.parentNode) resultLine.parentNode.removeChild(resultLine);
    resultLine = el("div", {
      "data-testid": "backend-deploy-result",
      text,
      style: `font-size:11px;color:${color || "#aaa"};margin-top:6px;`,
    });
    actionsRow.parentNode.insertBefore(resultLine, logPanel);
  }

  function customNodeActionSucceeded(resp) {
    return !!(resp && typeof resp === "object" && !resp._httpStatus && resp.status !== "error");
  }

  async function onCustomNodeSyncClicked(action) {
    const isPush = action === "push";
    const button = isPush ? pushPluginsBtn : rebuildDependenciesBtn;
    if (button.disabled) return;
    if (isPush) state.pushBusy = true;
    else state.rebuildBusy = true;
    syncButtons();

    let resp = null;
    try {
      resp = await (isPush ? triggerPushPlugins(apiBase) : triggerRebuildDependencies(apiBase));
      if (customNodeActionSucceeded(resp)) {
        appendBoundedResult(isPush ? "Push plugins request accepted." : "Dependency rebuild request accepted.", "#7ed321");
      } else {
        appendBoundedResult(
          isPush
            ? "Push plugins is not available yet — the sync endpoint is not ready."
            : "Rebuild dependencies is not available yet — the sync endpoint is not ready.",
          "#e05050"
        );
      }
    } catch {
      appendBoundedResult(
        isPush
          ? "Push plugins is not available yet — the sync endpoint is not ready."
          : "Rebuild dependencies is not available yet — the sync endpoint is not ready.",
        "#e05050"
      );
    } finally {
      await readCustomNodeSyncStatus();
      if (isPush) state.pushBusy = false;
      else state.rebuildBusy = false;
      syncButtons();
    }
  }

  // ── Redeploy + Restart (legacy semantics, bounded) ──────────────────────

  async function onRestartClicked() {
    if (restartBtn.disabled) return;
    state.redeployBusy = true;
    state.deploying = true;
    syncButtons();
    const setLabel = (t) => { restartBtn.textContent = t; };

    setLabel("Deploying\u2026");
    let deployResp = null;
    try { deployResp = await triggerDeploy(apiBase); } catch { deployResp = null; }
    if (!deployResp || !(deployResp.status === "started" || deployResp.status === "already_deploying")) {
      state.redeployBusy = false;
      state.deploying = false;
      setLabel("Redeploy and Restart");
      syncButtons();
      appendBoundedResult((deployResp && (deployResp.message || deployResp.error)) || "Deploy request failed.", "#e05050");
      return;
    }
    await readStatus();
    armStatusPoll();

    setLabel("Waiting for deploy\u2026");
    const started = Date.now();
    let ready = false;
    while ((Date.now() - started) < REDEPLOY_POLL_TIMEOUT_MS) {
      await new Promise((r) => setTimeout(r, STATUS_POLL_MS));
      const s = await readStatus();
      if (s.state === "ready") { ready = true; break; }
      if (s.state === "error") {
        state.redeployBusy = false;
        state.deploying = false;
        setLabel("Redeploy and Restart");
        syncButtons();
        appendBoundedResult(s.message || "Deploy failed.", "#e05050");
        return;
      }
    }
    if (!ready) {
      state.redeployBusy = false;
      state.deploying = false;
      setLabel("Deploy timed out");
      syncButtons();
      setTimeout(() => { restartBtn.textContent = "Redeploy and Restart"; }, 3000);
      return;
    }

    setLabel("Restarting ComfyUI\u2026");
    try { await fetch("/api/manager/restart", { method: "POST" }); } catch { /* connection may close first */ }

    setLabel("Waiting for restart\u2026");
    await new Promise((r) => setTimeout(r, 3000));
    const restartStart = Date.now();
    let serverUp = false;
    while ((Date.now() - restartStart) < RESTART_POLL_TIMEOUT_MS) {
      await new Promise((r) => setTimeout(r, STATUS_POLL_MS));
      try {
        const resp = await fetch("/api/object_info", { signal: AbortSignal.timeout(5000) });
        if (resp.ok) { serverUp = true; break; }
      } catch { /* keep waiting */ }
    }
    if (!serverUp) {
      state.redeployBusy = false;
      state.deploying = false;
      setLabel("Restart timed out");
      syncButtons();
      setTimeout(() => { restartBtn.textContent = "Redeploy and Restart"; }, 5000);
      return;
    }

    try { sessionStorage.setItem("_comfymodal_redeploy_restart_done", "1"); } catch {}
    setLabel("Reloading\u2026");
    location.reload();
  }

  // ── Log viewer ──────────────────────────────────────────────────────────

  async function refreshLog() {
    let data = null;
    try { data = await getDeployLog(apiBase); } catch { data = null; }
    const text = (data && typeof data.log === "string") ? tailLines(data.log, LOG_TAIL_LINES) : "(log unavailable)";
    logPre.textContent = text || "(empty log)";
  }

  function toggleLog(show) {
    state.logVisible = show;
    logPanel.style.display = show ? "block" : "none";
    logToggleBtn.textContent = show ? "Hide Deploy Log" : "Show Deploy Log";
    if (show) {
      while (logPanel.firstChild) logPanel.removeChild(logPanel.firstChild);
      logPanel.appendChild(el("div", { style: "display:flex;align-items:center;gap:8px;" }, [
        el("span", { text: `Deploy log (last ${LOG_TAIL_LINES} lines)`, style: "font-size:11px;color:#888;font-weight:600;" }),
        logRefreshBtn,
      ]));
      logPanel.appendChild(logPre);
      refreshLog();
    } else if (state.logTimer) {
      clearTimeout(state.logTimer);
      state.logTimer = null;
    }
  }

  // ── Wiring ──────────────────────────────────────────────────────────────

  deployBtn.addEventListener("click", onDeployClicked);
  restartBtn.addEventListener("click", onRestartClicked);
  pushPluginsBtn.addEventListener("click", () => onCustomNodeSyncClicked("push"));
  rebuildDependenciesBtn.addEventListener("click", () => onCustomNodeSyncClicked("rebuild"));
  refreshBtn.addEventListener("click", () => {
    Promise.all([readStatus(), readCustomNodeSyncStatus()]).then(emitDeployState);
  });
  logToggleBtn.addEventListener("click", () => toggleLog(!state.logVisible));
  logRefreshBtn.addEventListener("click", refreshLog);

  if (bus && typeof bus.on === "function") {
    bus.on("workspace-changed", () => {
      // A workspace swap may have started a deploy — re-read truth only.
      Promise.all([readStatus(), readCustomNodeSyncStatus()]).then(emitDeployState);
    });
  }

  // Mount performs a READ-ONLY status fetch. It never triggers a deploy.
  readStatus();
  readCustomNodeSyncStatus();

  container.appendChild(root);
  return root;
}
