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

export function renderDeploymentSection(container, apiBase, bus) {
  const state = {
    status: null,          // normalized server truth
    deploying: false,      // user-visible in-flight flag for THIS page's actions
    pollTimer: null,
    logTimer: null,
    logVisible: false,
    redeployBusy: false,
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
  const logToggleBtn = el("button", {
    type: "button", text: "Show Deploy Log",
    "data-testid": "backend-deploy-log-toggle",
    style: "width:auto;padding:5px 12px;font-size:11px;",
  });
  const actionsRow = el("div", { class: "comfymodal-studio-backend-actions", style: "flex-wrap:wrap;margin-bottom:8px;" }, [
    deployBtn, restartBtn, refreshBtn, logToggleBtn,
  ]);

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

  function syncButtons() {
    const busy = state.deploying || state.redeployBusy;
    deployBtn.disabled = busy;
    restartBtn.disabled = busy;
    deployBtn.textContent = state.deploying ? "Deploying\u2026" : "Deploy";
  }

  async function readStatus() {
    let data = null;
    try { data = await getDeployStatus(apiBase); } catch { data = null; }
    state.status = normalizeDeployStatus(data);
    renderStatus();
    return state.status;
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
  refreshBtn.addEventListener("click", () => { readStatus().then(emitDeployState); });
  logToggleBtn.addEventListener("click", () => toggleLog(!state.logVisible));
  logRefreshBtn.addEventListener("click", refreshLog);

  if (bus && typeof bus.on === "function") {
    bus.on("workspace-changed", () => {
      // A workspace swap may have started a deploy — re-read truth only.
      readStatus().then(emitDeployState);
    });
  }

  // Mount performs a READ-ONLY status fetch. It never triggers a deploy.
  readStatus();

  container.appendChild(root);
  return root;
}
