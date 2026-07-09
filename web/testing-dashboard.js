import { getDeployStatus, getExperiments, getExperimentHistory, bootstrapLoader } from "./testing-api.js";

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

function openSetupTab() {
  if (typeof window.open_testing_modal === "function") {
    window.open_testing_modal("setup");
  }
}

function openResultsTab() {
  if (typeof window.open_testing_modal === "function") {
    window.open_testing_modal("results");
  }
}

function openSettings() {
  if (typeof window.open_comfymodal_settings === "function") {
    window.open_comfymodal_settings();
  }
}

function openComparisonProfiles() {
  if (typeof window.open_testing_modal === "function") {
    window.open_testing_modal("profiles");
  } else if (typeof window.openComparisonProfilesOverlay === "function") {
    window.openComparisonProfilesOverlay();
  }
}

function openComparisonRunner() {
  if (typeof window.openComparisonRunnerOverlay === "function") {
    window.openComparisonRunnerOverlay();
  }
}

// ── Healthy state: strong primary CTA group ────────────────

function buildHealthyHeader(spec) {
  return el("section", { class: "testing-dashboard-primary-actions" }, [
    el("button", {
      class: "comfymodal-primary-btn testing-dashboard-cta-main",
      text: "New Experiment",
      onclick: openSetupTab,
    }),
    el("div", { class: "testing-dashboard-secondary-actions" }, [
      spec.activeExpCount > 0 ? el("button", {
        class: "comfymodal-secondary-btn",
        text: `Resume Active (${spec.activeExpCount})`,
        onclick: openResultsTab,
      }) : null,
      el("button", {
        class: "comfymodal-secondary-btn",
        text: "Open Results",
        onclick: openResultsTab,
      }),
    ]),
  ]);
}

// ── Utility toolbar (subordinate) ─────────────────────────

function buildUtilityToolbar() {
  return el("div", { class: "testing-dashboard-utility-toolbar" }, [
    el("button", { class: "comfymodal-secondary-btn", text: "Comparison Profiles", onclick: openComparisonProfiles }),
    el("button", { class: "comfymodal-secondary-btn", text: "Quick Comparison", onclick: openComparisonRunner }),
    el("button", { class: "comfymodal-secondary-btn", text: "Settings", onclick: openSettings }),
  ]);
}

// ── Metric cards with hierarchy ───────────────────────────

function buildMetricCards(spec) {
  return el("div", { class: "testing-dashboard-metrics" }, [
    el("article", { class: "testing-dashboard-metric testing-dashboard-metric-primary" }, [
      el("h3", { text: "Experiments" }),
      el("div", { style: "font-size:var(--font-size-lg,14px);font-weight:var(--font-weight-semibold,600);color:var(--color-text-primary,#e1e4ea);" }, [
        el("span", { text: `${spec.totalExps || 0} total` }),
        spec.activeExpCount > 0 ? el("span", { style: "color:var(--color-warning,#f59e0b);margin-left:12px;", text: `${spec.activeExpCount} active` }) : null,
      ]),
    ]),
    el("div", { class: "testing-dashboard-metrics-secondary", style: "display:flex;flex-direction:column;gap:var(--space-md,12px);" }, [
      el("article", { class: "testing-dashboard-metric" }, [
        el("h3", { text: "Workers" }),
        el("div", { style: "font-size:var(--font-size-sm,12px);color:var(--color-text-secondary,#9aa3b2);", text: `Active workers: ${spec.workerCount || 0}` }),
      ]),
      el("article", { class: "testing-dashboard-metric" }, [
        el("h3", { text: "Last Run" }),
        spec.lastRun
          ? el("div", { style: "font-size:var(--font-size-sm,12px);color:var(--color-text-secondary,#9aa3b2);display:flex;flex-direction:column;gap:4px;" }, [
              el("span", { text: spec.lastRun.run_id || "unknown run" }),
              el("span", { text: `${spec.lastRun.kind || "run"} \u00b7 ${spec.lastRun.status || "unknown"}` }),
            ])
          : el("div", { style: "font-size:var(--font-size-sm,12px);color:var(--color-text-muted,#6f7785);", text: "No recorded runs yet" }),
      ]),
    ]),
  ]);
}

// ── Blocked / unhealthy state hero ────────────────────────────

function buildDeployHero(state, message) {
  return el("div", { class: "comfymodal-hero", style: "margin-bottom:var(--space-lg,16px);" }, [
    el("h3", { text: "Deployment Required" }),
    el("div", { style: "font-size:var(--font-size-sm,12px);color:var(--color-text-secondary,#9aa3b2);line-height:1.5;" }, [
      el("span", { text: `Status: ` }),
      el("span", {
        class: "comfymodal-status-badge",
        style: `background:${state === "deploying" ? "var(--color-warning-bg)" : "var(--color-danger-bg)"};color:${state === "deploying" ? "var(--color-warning)" : "var(--color-danger)"};`,
        text: state || "unknown",
      }),
      message ? el("span", { style: "margin-left:8px;", text: message }) : null,
    ]),
    el("div", { style: "display:flex;gap:8px;margin-top:4px;" }, [
      el("button", { class: "comfymodal-primary-btn", text: "Open Setup", onclick: openSetupTab }),
    ]),
  ]);
}

// ── Public render ────────────────────────────────────────────

export function dashboard_tab_render(rootEl, api, options = {}) {
  const apiBase = options.apiBase || "/comfymodal";
  while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);

  const container = document.createElement("div");
  container.style.cssText = "display:flex;flex-direction:column;gap:16px;";
  rootEl.appendChild(container);

  const loader = bootstrapLoader(container, async () => {
    const [deploy, exps, history] = await Promise.all([
      getDeployStatus(apiBase),
      getExperiments(apiBase),
      getExperimentHistory(apiBase),
    ]);

    while (container.firstChild) container.removeChild(container.firstChild);

    const runs = (history && history.runs) || [];
    const expsList = (exps && exps.experiments) || [];
    const activeExps = expsList.filter((e) => {
      const status = e?.snapshot?.status || e?.status;
      return status === "running" || status === "started" || status === "paused";
    });
    const workerCount = expsList.reduce((count, experiment) => {
      const checkpoints = experiment?.snapshot?.checkpoints || {};
      return count + Object.values(checkpoints).filter((checkpoint) => checkpoint && checkpoint.status && checkpoint.status !== "completed").length;
    }, 0);

    const spec = {
      deployState: (deploy && deploy.state) || "unknown",
      deployMessage: (deploy && deploy.message) || null,
      totalExps: expsList.length,
      activeExpCount: activeExps.length,
      workerCount,
      lastRun: runs.length > 0 ? runs[0] : null,
    };

    const isUnhealthy = !deploy || deploy.state === "unknown" || deploy.state === "failed" || deploy.state === "deploying" || deploy.state === "unhealthy";

    if (isUnhealthy) {
      container.appendChild(buildDeployHero(spec.deployState, spec.deployMessage));
      container.appendChild(buildMetricCards(spec));
    } else {
      container.appendChild(buildHealthyHeader(spec));
      container.appendChild(buildUtilityToolbar());
      container.appendChild(buildMetricCards(spec));
    }
  });

  loader.attempt();
}
