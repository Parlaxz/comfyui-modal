// Modal Studio — Experiment Mode
//
// Experiment mode is an overlay on Playground controls, not a separate page.
// When enabled:
//   - The top toggle becomes "Exit Experiment"
//   - A Compare Backends block appears
//   - A matrix summary block appears
//   - Existing eligible controls gain experiment-axis checkboxes beside their labels
//
// Axis editing is attached to each control in-place, not via a separate
// master list page. Run Experiment may be disabled with a precise reason.

import { CONTROL_DEFS } from "./studio-feature-registry.js";

// ── Experiment toggle ────────────────────────────────────────────────────

export function renderExperimentToggle(state, actions) {
  const isActive = state.playground && state.playground.experimentMode;
  const container = document.createElement("div");
  container.className = "comfymodal-studio-experiment-toggle";

  const btn = document.createElement("button");
  btn.className = isActive
    ? "comfymodal-primary-btn comfymodal-studio-experiment-active"
    : "comfymodal-secondary-btn";
  btn.textContent = isActive ? "Exit Experiment" : "Experiment";
  btn.setAttribute("data-testid", "experiment-toggle");
  btn.addEventListener("click", () => {
    if (actions && actions.setExperimentMode) {
      actions.setExperimentMode(!isActive);
    }
  });
  container.appendChild(btn);
  return container;
}

// ── Compare Backends block ───────────────────────────────────────────────

export function renderCompareBackends(state, actions) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-compare-backends";
  container.setAttribute("data-testid", "compare-backends");

  const heading = document.createElement("h4");
  heading.className = "comfymodal-studio-block-heading";
  heading.textContent = "Compare Backends";
  container.appendChild(heading);

  const desc = document.createElement("p");
  desc.className = "comfymodal-studio-empty-state";
  desc.textContent = "Select backends to compare. Configure backends in Settings > Legacy Setup.";
  container.appendChild(desc);

  const list = document.createElement("div");
  list.className = "comfymodal-studio-compare-list";
  container.appendChild(list);

  return container;
}

// ── Matrix Summary block ─────────────────────────────────────────────────

export function renderMatrixSummary(state, actions) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-matrix-summary";
  container.setAttribute("data-testid", "matrix-summary");

  const heading = document.createElement("h4");
  heading.className = "comfymodal-studio-block-heading";
  heading.textContent = "Matrix Summary";
  container.appendChild(heading);

  const body = document.createElement("div");
  body.className = "comfymodal-studio-matrix-body";
  body.setAttribute("data-testid", "matrix-body");
  container.appendChild(body);

  // Update matrix summary based on current axes
  updateMatrixSummary(body, state);

  return container;
}

function updateMatrixSummary(body, state) {
  while (body.firstChild) body.removeChild(body.firstChild);

  const axes = (state.playground && state.playground.experimentAxes) || {};
  const axisEntries = Object.entries(axes).filter(([, def]) => def && def.enabled);

  if (axisEntries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "comfymodal-studio-empty-state";
    empty.textContent = "Check boxes next to controls to add them as experiment axes.";
    body.appendChild(empty);
    return;
  }

  const totalCombos = axisEntries.reduce((prod, [, def]) => {
    const vals = (def.values && def.values.length) || 1;
    return prod * vals;
  }, 1);

  const list = document.createElement("ul");
  list.className = "comfymodal-studio-matrix-axis-list";
  axisEntries.forEach(([ctrlId, def]) => {
    const ctrl = CONTROL_DEFS[ctrlId] || {};
    const item = document.createElement("li");
    const vals = (def.values && def.values.length) || 1;
    item.textContent = `${ctrl.label || ctrlId}: ${vals} value(s)`;
    list.appendChild(item);
  });
  body.appendChild(list);

  const summary = document.createElement("p");
  summary.className = "comfymodal-studio-matrix-total";
  summary.textContent = `Total combinations: ${totalCombos}`;
  body.appendChild(summary);
}

// ── Axis checkbox enhancement ────────────────────────────────────────────
//
// Adds an experiment-axis checkbox beside a control's label. The checkbox
// toggles whether the control participates as an experiment axis.

export function enhanceControlWithAxisCheckbox(controlEl, controlId, state, actions) {
  if (!controlEl) return;

  const axes = (state.playground && state.playground.experimentAxes) || {};
  const isAxis = !!(axes[controlId] && axes[controlId].enabled);

  const wrapper = document.createElement("label");
  wrapper.className = "comfymodal-studio-axis-checkbox-wrapper";
  wrapper.setAttribute("data-testid", `axis-checkbox-${controlId}`);

  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = isAxis;
  cb.setAttribute("data-axis", controlId);
  cb.className = "comfymodal-studio-axis-checkbox";
  cb.addEventListener("change", () => {
    if (actions && actions.toggleExperimentAxis) {
      actions.toggleExperimentAxis(controlId, cb.checked);
    }
  });

  wrapper.appendChild(cb);
  return wrapper;
}

// ── Disabled Run Experiment explanation ──────────────────────────────────

export function renderRunExperimentDisabledReason(state, actions) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-disabled-reason";
  container.setAttribute("data-testid", "run-experiment-disabled");

  const msg = document.createElement("p");
  msg.textContent = "Run Experiment is not yet wired to the backend. ";
  msg.style.color = "var(--color-text-secondary)";
  msg.style.fontSize = "var(--font-size-sm)";

  const link = document.createElement("a");
  link.href = "#";
  link.textContent = "Go to Legacy Setup to run experiments.";
  link.style.color = "var(--color-accent)";
  link.style.cursor = "pointer";
  link.addEventListener("click", (e) => {
    e.preventDefault();
    if (actions && actions.navigateToLegacySetup) {
      actions.navigateToLegacySetup();
    }
  });

  msg.appendChild(document.createTextNode(" "));
  msg.appendChild(link);
  container.appendChild(msg);
  return container;
}

// ── Full experiment mode renderer ────────────────────────────────────────

export function renderExperimentMode(state, actions) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-experiment-mode";
  container.setAttribute("data-testid", "experiment-mode");

  // Compare Backends block
  container.appendChild(renderCompareBackends(state, actions));

  // Matrix Summary block
  container.appendChild(renderMatrixSummary(state, actions));

  // Disabled Run Experiment explanation
  const runBtn = document.createElement("button");
  runBtn.className = "comfymodal-primary-btn";
  runBtn.disabled = true;
  runBtn.textContent = "Run Experiment";
  runBtn.setAttribute("data-testid", "run-experiment-btn");
  runBtn.title = "Run Experiment is not yet wired. Use Legacy Setup.";
  container.appendChild(runBtn);

  container.appendChild(renderRunExperimentDisabledReason(state, actions));

  return container;
}
