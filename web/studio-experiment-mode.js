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
import { getBackends, getCompareBackends } from "./studio-backend.js";

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

export function renderCompareBackends(state, actions, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-compare-backends";
  container.setAttribute("data-testid", "compare-backends");

  const heading = document.createElement("h4");
  heading.className = "comfymodal-studio-block-heading";
  heading.textContent = "Compare Backends";
  container.appendChild(heading);

  const list = document.createElement("div");
  list.className = "comfymodal-studio-compare-list";
  container.appendChild(list);

  // Fetch backends through the Studio backend abstraction (context passed explicitly)
  const apiBase = (context && context.apiBase) || "/comfymodal";
  getBackends({ apiBase }).then((backends) => {
    while (list.firstChild) list.removeChild(list.firstChild);

    if (!backends || backends.length === 0) {
      const emptyState = document.createElement("p");
      emptyState.className = "comfymodal-studio-empty-state";
      // Link to the Backend tab instead of Legacy Setup
      const link = document.createElement("a");
      link.href = "#";
      link.textContent = "Go to Backend tab";
      link.style.color = "var(--color-accent)";
      link.style.cursor = "pointer";
      link.addEventListener("click", (e) => {
        e.preventDefault();
        if (actions && actions.navigateToBackendTab) {
          actions.navigateToBackendTab();
        }
      });
      emptyState.textContent = "No backends configured. ";
      emptyState.appendChild(link);
      emptyState.appendChild(document.createTextNode(" to add backends."));
      list.appendChild(emptyState);
      return;
    }

    // Read currently selected compare backend IDs from state
    const compareIds = (state.playground && state.playground.compareBackendIds) || [];

    backends.forEach((b) => {
      const bId = b.id || b.label || "";
      const item = document.createElement("div");
      item.className = "comfymodal-studio-compare-item";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "comfymodal-studio-compare-checkbox";
      cb.setAttribute("data-backend-id", bId);
      // Sync checked state from compareBackendIds
      cb.checked = compareIds.includes(bId);
      cb.addEventListener("change", () => {
        const current = (state.playground && state.playground.compareBackendIds) || [];
        let updated;
        if (cb.checked) {
          updated = [...current, bId];
        } else {
          updated = current.filter((id) => id !== bId);
        }
        state.playground.compareBackendIds = updated;
        // Re-render matrix summary by re-running updateMatrixSummary on the existing body
        const matrixBody = container.parentNode
          ? container.parentNode.querySelector('[data-testid="matrix-body"]')
          : null;
        if (matrixBody) {
          updateMatrixSummary(matrixBody, state);
        }
      });
      item.appendChild(cb);
      const label = document.createElement("span");
      label.textContent = b.label || b.id || "Unknown";
      label.style.fontSize = "var(--font-size-sm)";
      item.appendChild(label);
      list.appendChild(item);
    });
  }).catch(() => {
    const errorMsg = document.createElement("p");
    errorMsg.className = "comfymodal-studio-empty-state";
    errorMsg.textContent = "Could not load backends.";
    list.appendChild(errorMsg);
  });

  return container;
}

// ── Matrix Summary block ─────────────────────────────────────────────────

export function renderMatrixSummary(state, actions) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-matrix-summary";
  container.setAttribute("data-testid", "matrix-summary");

  const headingRow = document.createElement("div");
  headingRow.style.display = "flex";
  headingRow.style.alignItems = "center";
  headingRow.style.gap = "6px";

  const heading = document.createElement("h4");
  heading.className = "comfymodal-studio-block-heading";
  heading.textContent = "Matrix Summary";
  headingRow.appendChild(heading);

  // Info hint for matrix summary
  const infoHint = document.createElement("span");
  infoHint.className = "comfymodal-studio-info-hint";
  infoHint.tabIndex = 0;
  infoHint.role = "tooltip";
  infoHint.setAttribute("aria-label", "Configure axes by checking boxes beside controls. The matrix shows total combinations across all active axes and selected backends.");
  infoHint.textContent = "\u24d8";
  const tooltip = document.createElement("span");
  tooltip.className = "comfymodal-studio-tooltip";
  tooltip.textContent = "Configure axes by checking boxes beside controls. The matrix shows total combinations across all active axes and selected backends.";
  infoHint.appendChild(tooltip);
  infoHint.addEventListener("mouseenter", () => { tooltip.style.display = "block"; });
  infoHint.addEventListener("mouseleave", () => { tooltip.style.display = ""; });
  infoHint.addEventListener("focus", () => { tooltip.style.display = "block"; });
  infoHint.addEventListener("blur", () => { tooltip.style.display = ""; });
  headingRow.appendChild(infoHint);

  container.appendChild(headingRow);

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

  // Count backends: base selectedBackendId + compareBackendIds
  const baseBackend = (state.playground && state.playground.selectedBackendId) || "";
  const compareIds = (state.playground && state.playground.compareBackendIds) || [];
  const allBackendIds = baseBackend ? [baseBackend, ...compareIds] : [...compareIds];
  const uniqueBackendIds = [...new Set(allBackendIds.filter(Boolean))];
  const backendCount = uniqueBackendIds.length;

  if (axisEntries.length === 0 && backendCount === 0) {
    const empty = document.createElement("p");
    empty.className = "comfymodal-studio-empty-state";
    empty.textContent = "Check boxes next to controls to add them as experiment axes.";
    body.appendChild(empty);

    // Warning if zero axes
    const warn = document.createElement("p");
    warn.className = "comfymodal-studio-matrix-warning";
    warn.textContent = "\u26a0 No axes configured. Add at least one axis to create an experiment matrix.";
    warn.style.fontSize = "var(--font-size-xs)";
    warn.style.color = "var(--color-warning)";
    warn.style.marginTop = "4px";
    body.appendChild(warn);
    return;
  }

  const totalCombos = axisEntries.reduce((prod, [, def]) => {
    const vals = (def.values && def.values.length) || 1;
    return prod * vals;
  }, 1);

  const list = document.createElement("ul");
  list.className = "comfymodal-studio-matrix-axis-list";
  list.style.fontSize = "var(--font-size-xs)";
  list.style.margin = "4px 0";
  list.style.paddingLeft = "16px";
  axisEntries.forEach(([ctrlId, def]) => {
    const ctrl = CONTROL_DEFS[ctrlId] || {};
    const item = document.createElement("li");
    const vals = (def.values && def.values.length) || 1;
    item.textContent = `${ctrl.label || ctrlId}: ${vals} value(s)`;
    list.appendChild(item);
  });
  body.appendChild(list);

  // Summary stats
  const stats = document.createElement("div");
  stats.style.fontSize = "var(--font-size-xs)";
  stats.style.marginTop = "4px";

  const axisCount = document.createElement("p");
  axisCount.textContent = `Active axes: ${axisEntries.length}`;
  stats.appendChild(axisCount);

  if (backendCount > 0) {
    const backendStat = document.createElement("p");
    backendStat.textContent = `Selected backends: ${backendCount}`;
    stats.appendChild(backendStat);
  } else {
    const noBackend = document.createElement("p");
    noBackend.textContent = "No backends selected.";
    noBackend.style.color = "var(--color-text-muted)";
    stats.appendChild(noBackend);
  }

  const estimatedRuns = totalCombos * Math.max(backendCount, 1);
  const totalSummary = document.createElement("p");
  totalSummary.style.fontWeight = "var(--font-weight-semibold)";
  totalSummary.textContent = `Estimated runs: ${estimatedRuns}`;
  stats.appendChild(totalSummary);

  body.appendChild(stats);

  // Warning if zero or no backends
  if (axisEntries.length === 0) {
    const warn = document.createElement("p");
    warn.className = "comfymodal-studio-matrix-warning";
    warn.textContent = "\u26a0 No axes configured. Add at least one axis.";
    warn.style.color = "var(--color-warning)";
    warn.style.marginTop = "4px";
    body.appendChild(warn);
  }
}

// ── Axis checkbox enhancement ────────────────────────────────────────────
//
// Adds an experiment-axis checkbox beside a control's label. The checkbox
// toggles whether the control participates as an experiment axis.
// When checked, an inline axis editor is shown.

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

  // If axis is active, insert the inline axis editor after the control group
  if (isAxis) {
    const editor = renderAxisEditor(controlId, state, actions);
    if (editor) {
      // Schedule insertion after controlEl's parent processes
      setTimeout(() => {
        const parent = controlEl.parentNode;
        if (parent && parent.nextSibling) {
          parent.insertBefore(editor, parent.nextSibling);
        } else if (parent) {
          parent.appendChild(editor);
        }
      }, 0);
    }
  }

  return wrapper;
}

// ── Axis Editor ──────────────────────────────────────────────────────────
//
// Renders an inline axis editor for a given control. Supports:
//   - textarea (prompt/instruction): multiline variants textarea
//   - number (steps, guidance, etc.): comma-separated values with validation
//   - select (LoRA/backend): disabled with explanation

export function renderAxisEditor(controlId, state, actions) {
  const def = CONTROL_DEFS[controlId];
  if (!def) return null;

  const axisData = (state.playground && state.playground.experimentAxes && state.playground.experimentAxes[controlId]) || {};
  const currentValues = axisData.values || [def.defaultValue != null ? String(def.defaultValue) : ""];

  const editor = document.createElement("div");
  editor.className = "comfymodal-studio-axis-editor";
  editor.setAttribute("data-testid", `axis-editor-${controlId}`);

  const modeRow = document.createElement("div");
  modeRow.className = "comfymodal-studio-axis-editor-mode";

  const modeLabel = document.createElement("span");
  modeLabel.textContent = "Mode:";
  modeLabel.style.fontSize = "var(--font-size-xs)";
  modeLabel.style.marginRight = "6px";
  modeRow.appendChild(modeLabel);

  const modeDefaults = document.createElement("label");
  modeDefaults.style.fontSize = "var(--font-size-xs)";
  modeDefaults.style.marginRight = "8px";
  const defaultRadio = document.createElement("input");
  defaultRadio.type = "radio";
  defaultRadio.name = `axis-mode-${controlId}`;
  defaultRadio.value = "defaults";
  defaultRadio.checked = true;
  modeDefaults.appendChild(defaultRadio);
  modeDefaults.appendChild(document.createTextNode(" Defaults"));
  modeRow.appendChild(modeDefaults);

  const modeAll = document.createElement("label");
  modeAll.style.fontSize = "var(--font-size-xs)";
  const allRadio = document.createElement("input");
  allRadio.type = "radio";
  allRadio.name = `axis-mode-${controlId}`;
  allRadio.value = "all";
  modeAll.appendChild(allRadio);
  modeAll.appendChild(document.createTextNode(" All Selected Axes"));
  modeRow.appendChild(modeAll);

  editor.appendChild(modeRow);

  // Values area
  const valuesArea = document.createElement("div");
  valuesArea.className = "comfymodal-studio-axis-editor-values";

  if (def.type === "textarea") {
    // Multiline variants textarea for prompt/instruction
    const textarea = document.createElement("textarea");
    textarea.className = "comfymodal-input comfymodal-studio-textarea";
    textarea.placeholder = "Enter prompt variants, one per line\u2026";
    textarea.rows = 3;
    textarea.value = currentValues.join("\n");
    textarea.style.fontSize = "var(--font-size-xs)";
    textarea.addEventListener("input", () => {
      const lines = textarea.value.split("\n").filter((l) => l.trim());
      if (actions && actions.updateExperimentAxisValues) {
        actions.updateExperimentAxisValues(controlId, lines.length > 0 ? lines : [def.defaultValue || ""]);
      }
    });
    valuesArea.appendChild(textarea);
  } else if (def.type === "number") {
    // Comma-separated values input for numeric controls
    const input = document.createElement("input");
    input.type = "text";
    input.className = "comfymodal-input";
    input.placeholder = "e.g. 20, 30, 40";
    input.value = currentValues.join(", ");
    input.style.fontSize = "var(--font-size-xs)";
    input.addEventListener("input", () => {
      const parts = input.value.split(",").map((s) => s.trim()).filter((s) => s !== "");
      const nums = parts.map(Number).filter((n) => !isNaN(n));
      if (nums.length > 0) {
        if (actions && actions.updateExperimentAxisValues) {
          actions.updateExperimentAxisValues(controlId, nums);
        }
      }
    });
    valuesArea.appendChild(input);

    // Quick-add buttons for common steps values
    if (controlId === "steps") {
      const quickRow = document.createElement("div");
      quickRow.style.marginTop = "4px";
      quickRow.style.display = "flex";
      quickRow.style.gap = "4px";
      [10, 20, 30, 50].forEach((v) => {
        const btn = document.createElement("button");
        btn.className = "comfymodal-secondary-btn";
        btn.textContent = String(v);
        btn.style.fontSize = "10px";
        btn.style.padding = "2px 6px";
        btn.addEventListener("click", () => {
          const current = input.value.split(",").map((s) => s.trim()).filter((s) => s !== "");
          if (!current.includes(String(v))) {
            input.value = current.concat(String(v)).join(", ");
            if (actions && actions.updateExperimentAxisValues) {
              actions.updateExperimentAxisValues(controlId, current.concat(v).map(Number));
            }
          }
        });
        quickRow.appendChild(btn);
      });
      valuesArea.appendChild(quickRow);
    }

    // Quick-add for guidance
    if (controlId === "guidance") {
      const quickRow = document.createElement("div");
      quickRow.style.marginTop = "4px";
      quickRow.style.display = "flex";
      quickRow.style.gap = "4px";
      [5, 7, 10, 15].forEach((v) => {
        const btn = document.createElement("button");
        btn.className = "comfymodal-secondary-btn";
        btn.textContent = String(v);
        btn.style.fontSize = "10px";
        btn.style.padding = "2px 6px";
        btn.addEventListener("click", () => {
          const current = input.value.split(",").map((s) => s.trim()).filter((s) => s !== "");
          if (!current.includes(String(v))) {
            input.value = current.concat(String(v)).join(", ");
            if (actions && actions.updateExperimentAxisValues) {
              actions.updateExperimentAxisValues(controlId, current.concat(v).map(Number));
            }
          }
        });
        quickRow.appendChild(btn);
      });
      valuesArea.appendChild(quickRow);
    }
  } else if (def.type === "select") {
    // Disabled with explanation for select controls like LoRA
    const disabledMsg = document.createElement("p");
    disabledMsg.textContent = "Axis configuration not available for this control type. Configure in Legacy Setup.";
    disabledMsg.style.fontSize = "var(--font-size-xs)";
    disabledMsg.style.color = "var(--color-text-muted)";
    disabledMsg.style.fontStyle = "italic";
    valuesArea.appendChild(disabledMsg);
  }

  editor.appendChild(valuesArea);

  // Add/Update axis button
  const actionRow = document.createElement("div");
  actionRow.style.marginTop = "4px";
  actionRow.style.display = "flex";
  actionRow.style.gap = "4px";

  const updateBtn = document.createElement("button");
  updateBtn.className = "comfymodal-secondary-btn";
  updateBtn.textContent = "Update Axis";
  updateBtn.style.fontSize = "10px";
  updateBtn.style.padding = "2px 8px";
  updateBtn.addEventListener("click", () => {
    // Re-read values from the editor and update
    if (actions && actions.updateExperimentAxisValues) {
      // The input event handlers already update values; this is explicit confirmation
    }
  });
  actionRow.appendChild(updateBtn);

  const removeBtn = document.createElement("button");
  removeBtn.className = "comfymodal-destructive-btn";
  removeBtn.textContent = "Remove Axis";
  removeBtn.style.fontSize = "10px";
  removeBtn.style.padding = "2px 8px";
  removeBtn.addEventListener("click", () => {
    if (actions && actions.toggleExperimentAxis) {
      actions.toggleExperimentAxis(controlId, false);
    }
  });
  actionRow.appendChild(removeBtn);

  editor.appendChild(actionRow);

  return editor;
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

export function renderExperimentMode(state, actions, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-experiment-mode";
  container.setAttribute("data-testid", "experiment-mode");

  // Compare Backends block (context passed explicitly, not via _context on state)
  container.appendChild(renderCompareBackends(state, actions, context || {}));

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
