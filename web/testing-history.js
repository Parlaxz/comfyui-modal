import { getExperimentHistory, bootstrapLoader } from "./testing-api.js";

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    } else e.setAttribute(k, props[k]);
  }
  for (const c of (Array.isArray(children) ? children : [children])) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

function formatTime(ts) {
  if (!ts) return "\u2014";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return String(ts).slice(0, 10);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatDuration(run) {
  if (run.duration) {
    const sec = Math.round(run.duration / 1000);
    if (sec < 60) return `${sec}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
    return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
  }
  if (run.completed_at && run.created_at) {
    const dur = run.completed_at - run.created_at;
    if (dur > 0) { const sec = Math.round(dur / 1000); if (sec < 60) return `${sec}s`; return `${Math.floor(sec / 60)}m ${sec % 60}s`; }
  }
  return "\u2014";
}

function statusDotColor(status) {
  switch (status) {
    case "completed": return "var(--color-success,#4ade80)";
    case "running":
    case "started": return "var(--color-warning,#f59e0b)";
    case "failed": return "var(--color-danger,#ef4444)";
    default: return "var(--color-text-muted,#6f7785)";
  }
}

function shortLabel(text, maxLen) {
  if (!text) return "";
  return text.length > maxLen ? text.slice(0, maxLen) + "\u2026" : text;
}

function buildHistoryRow(run) {
  const name = run.run_id || run.prompt_id || "Untitled";
  const status = run.status || "unknown";
  const dotColor = statusDotColor(status);

  // Model/profile short label for secondary display
  const modelLabel = run.model || run.profile || "";

  return el("div", { class: "testing-history-row comfymodal-history-row", style: "flex-direction:column;align-items:stretch;padding:var(--space-sm,8px) var(--space-md,12px);" }, [
    // Top line: thumbnail + name
    el("div", { class: "testing-history-row-main" }, [
      el("div", { class: "testing-history-thumb", text: name.charAt(0).toUpperCase() }),
      el("span", { style: "font-size:var(--font-size-sm,12px);color:var(--color-text-primary,#e1e4ea);font-weight:var(--font-weight-medium,500);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;", text: shortLabel(name, 40) }),
    ]),
    // Bottom line: status + time + duration + model
    el("div", { class: "testing-history-row-meta" }, [
      el("span", { class: "testing-history-status", style: "display:flex;align-items:center;gap:4px;" }, [
        el("span", { class: "status-dot", style: `width:7px;height:7px;border-radius:50%;background:${dotColor};flex-shrink:0;` }),
        el("span", { text: status }),
      ]),
      el("span", { class: "testing-history-time", text: formatTime(run.created_at || run.created) }),
      el("span", { class: "testing-history-duration", text: formatDuration(run) }),
      modelLabel ? el("span", { class: "testing-history-model", title: modelLabel, text: shortLabel(modelLabel, 20) }) : null,
    ]),
  ]);
}

export function history_tab_render(rootEl, api, options = {}) {
  const apiBase = options.apiBase || "/comfymodal";
  while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);

  const container = document.createElement("div");
  container.style.cssText = "display:flex;flex-direction:column;gap:8px;";
  rootEl.appendChild(container);

  const loader = bootstrapLoader(container, async () => {
    const data = await getExperimentHistory(apiBase);
    while (container.firstChild) container.removeChild(container.firstChild);

    const header = el("h3", { style: "margin:0 0 8px;font-size:var(--font-size-lg,14px);font-weight:var(--font-weight-semibold,600);color:var(--color-text-primary,#e1e4ea);", text: "Run History" });
    container.appendChild(header);

    const runs = (data && data.runs) || [];
    if (runs.length === 0) {
      container.appendChild(el("div", { style: "font-size:var(--font-size-sm,12px);color:var(--color-text-muted,#6f7785);padding:12px;text-align:center;", text: "No recorded runs yet" }));
      return;
    }

    const list = el("div", { style: "display:flex;flex-direction:column;gap:4px;" });
    const sorted = [...runs].sort((a, b) => {
      const aTime = a.created_at || a.created || 0;
      const bTime = b.created_at || b.created || 0;
      return bTime - aTime;
    });
    for (const run of sorted) {
      list.appendChild(buildHistoryRow(run));
    }
    container.appendChild(list);
  });

  loader.attempt();
}
