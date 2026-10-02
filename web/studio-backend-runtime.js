// Modal Studio — Backend Runtime / Overview Section (H6 re-home)
//
// Read-only operational overview for the modern Backend page: current
// workspace identity, deployment state, Modal connection, and runtime
// health/readiness — all server-reported truth, refreshed on demand.
//
// Ownership boundary: preferences (GPU default, preview defaults, output
// preferences, tracing level) remain in Settings and are intentionally NOT
// mirrored here.

import { el } from "./studio-ui.js";
import {
  listWorkspacesRegistry,
  summarizeWorkspaces,
  getDeployStatus,
  normalizeDeployStatus,
  getAuthStatus,
  getRuntimeHealth,
} from "./studio-backend-api.js";

// Minimal pub/sub bus shared by Backend operational sections. Plain arrays —
// no DOM or global state involved.
export function createOpsBus() {
  const listeners = {};
  return {
    on(event, fn) {
      (listeners[event] = listeners[event] || []).push(fn);
    },
    emit(event) {
      for (const fn of (listeners[event] || []).slice()) {
        try { fn(); } catch { /* listener errors never break emitters */ }
      }
    },
  };
}

/** Pure: bounded read-only projection of the four operational probes. */
export function summarizeOperationalState({ registry, deploy, auth, health }) {
  const ws = summarizeWorkspaces(registry);
  const dep = normalizeDeployStatus(deploy);
  const connected = !!(auth && auth.connected === true);
  let healthState = "unknown";
  let healthMessage = "";
  if (health && typeof health === "object") {
    healthState = String(health.status || "unknown");
    healthMessage = String(health.message || "");
  }
  const healthLabel = healthState === "ok" ? "Ready"
    : healthState === "deploying" ? "Deploying"
    : healthMessage ? `${healthState} \u00b7 ${healthMessage}`
    : healthState;
  return {
    activeWorkspaceLabel: ws.activeLabel,
    hasActiveWorkspace: !!ws.activeId,
    deployState: dep.available ? dep.state : "unavailable",
    deployMessage: dep.message,
    modalConnected: connected,
    runtimeHealth: healthLabel,
  };
}

export function renderRuntimeSection(container, apiBase, bus) {
  const root = el("div", { class: "comfymodal-studio-backend-detail", "data-testid": "backend-runtime" });

  const card = el("div", { class: "comfymodal-studio-backend-detail-card", style: "margin-bottom:8px;" });
  card.appendChild(el("div", { text: "Operational Overview", style: "font-weight:600;font-size:12px;margin-bottom:8px;" }));

  const rowsWrap = el("div", { "data-testid": "backend-runtime-rows", style: "display:flex;flex-direction:column;gap:6px;" });
  card.appendChild(rowsWrap);

  const refreshBtn = el("button", {
    type: "button", text: "Refresh", "data-testid": "backend-runtime-refresh",
    style: "width:auto;padding:5px 14px;font-size:11px;margin-top:10px;",
  });
  card.appendChild(refreshBtn);
  card.appendChild(el("div", {
    text: "Preferences (GPU default, preview, outputs, tracing level) live in Settings.",
    style: "font-size:10px;color:#555;margin-top:8px;",
  }));

  root.appendChild(card);

  function row(label, testid) {
    const valueEl = el("span", {
      "data-testid": testid,
      text: "\u2026",
      style: "font-size:12px;color:#ccc;",
    });
    const r = el("div", { style: "display:flex;gap:8px;align-items:baseline;" }, [
      el("span", { text: label, style: "font-size:11px;color:#888;min-width:150px;" }),
      valueEl,
    ]);
    rowsWrap.appendChild(r);
    return valueEl;
  }

  const wsValue = row("Active workspace", "backend-runtime-workspace");
  const deployValue = row("Deployment", "backend-runtime-deploy");
  const authValue = row("Modal connection", "backend-runtime-auth");
  const healthValue = row("Runtime health", "backend-runtime-health");

  async function refresh() {
    let registry = null;
    let deploy = null;
    let auth = null;
    let health = null;
    try { registry = await listWorkspacesRegistry(apiBase); } catch { registry = null; }
    try { deploy = await getDeployStatus(apiBase); } catch { deploy = null; }
    try { auth = await getAuthStatus(apiBase); } catch { auth = null; }
    try { health = await getRuntimeHealth(apiBase); } catch { health = null; }
    const s = summarizeOperationalState({ registry, deploy, auth, health });

    wsValue.textContent = s.hasActiveWorkspace
      ? `${s.activeWorkspaceLabel} (server-resolved)`
      : "None configured";
    deployValue.textContent = s.deployState === "unavailable"
      ? "unavailable"
      : `${s.deployState}${s.deployMessage ? ` \u2014 ${s.deployMessage}` : ""}`;
    authValue.textContent = s.modalConnected ? "Connected" : "Not configured";
    healthValue.textContent = s.runtimeHealth;
  }

  refreshBtn.addEventListener("click", refresh);

  if (bus && typeof bus.on === "function") {
    bus.on("workspace-changed", refresh);
    bus.on("deploy-status-changed", refresh);
  }

  // Mount performs READ-ONLY probes only.
  refresh();

  container.appendChild(root);
  return root;
}
