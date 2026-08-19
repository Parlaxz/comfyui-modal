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

import { CONTROL_DEFS, getRecommendedSteps, getRecommendedStepsStatus, getLastFiniteSeed, cryptoRandomSeed } from "./studio-feature-registry.js";
import { runStudioExperiment, stopExperiment } from "./studio-backend-api.js";
import { getAxisEligibilityForPresets } from "./studio-preset-capabilities.js";
import {
  runExperimentV2,
  getExperimentV2Status,
  cancelExperimentV2,
  resumeExperiment,
  retryCell,
} from "./studio-backend-api.js";
import {
  createExperimentRunController,
  formatExperimentProgress,
} from "./studio-playground-run.js";
import { loadModalOptions } from "./studio-output-preferences.js";

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

// ── Axis eligibility helper ──────────────────────────────────────────────

function recalcEligibleAxes(state, loadedPresets) {
  const ids = getExperimentPresetIds(state);
  if (ids.length === 0) return [];
  const selectedPresets = ids
    .map((id) => (loadedPresets || []).find((p) => (p.id || p.label || "") === id))
    .filter(Boolean);
  const featureId = (state.playground && state.playground.featureId) || "txt2img";
  return getAxisEligibilityForPresets(selectedPresets, featureId);
}

// ── Helpers for collapsible and grouping ──────────────────────────────

/**
 * Create a collapsible toggle button with content panel.
 * Returns { summary, content } where both are live DOM elements.
 */
function _createCollapsible(labelText, isExpanded, testId) {
  var summary = document.createElement("button");
  summary.className = "comfymodal-studio-collapsible-summary";
  summary.setAttribute("aria-expanded", isExpanded ? "true" : "false");
  if (testId) summary.setAttribute("data-testid", testId);

  // Build arrow + label with safe DOM methods (no innerHTML for user text)
  var arrowSpan = document.createElement("span");
  arrowSpan.className = "arrow";
  arrowSpan.textContent = "\u25b6";
  summary.appendChild(arrowSpan);

  var labelSpan = document.createElement("span");
  labelSpan.textContent = labelText;
  summary.appendChild(labelSpan);

  summary.addEventListener("click", function () {
    var expanded = summary.getAttribute("aria-expanded") === "true";
    summary.setAttribute("aria-expanded", String(!expanded));
    content.classList.toggle("is-visible");
  });

  var content = document.createElement("div");
  content.className = "comfymodal-studio-collapsible-content" + (isExpanded ? " is-visible" : "");

  return { summary: summary, content: content };
}

/**
 * Group presets by their optional `group` field.
 * Returns { groups: { groupName: [preset, ...] }, ungrouped: [preset, ...] }
 */
function _groupPresetsByField(presets) {
  var groups = {};
  var ungrouped = [];
  presets.forEach(function (p) {
    var g = p.group;
    if (g && typeof g === "string" && g.trim() !== "") {
      if (!groups[g]) groups[g] = [];
      groups[g].push(p);
    } else {
      ungrouped.push(p);
    }
  });
  return { groups: groups, ungrouped: ungrouped };
}

// ── Compare Backends block ───────────────────────────────────────────────

export function renderCompareBackends(state, actions, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-compare-backends";
  container.setAttribute("data-testid", "compare-backends");

  const heading = document.createElement("h4");
  heading.className = "comfymodal-studio-block-heading";
  heading.textContent = "Compare Presets";
  container.appendChild(heading);

  // Main collapsible wrapper
  var mainCollapsible = _createCollapsible("Presets", false, "compare-presets-toggle");
  container.appendChild(mainCollapsible.summary);
  container.appendChild(mainCollapsible.content);

  const apiBase = (context && context.apiBase) || "/comfymodal";
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";

  // Lazy import keeps this module Node-importable for deterministic tests
  // (studio-backend.js pulls ComfyUI-only modules through its own graph).
  import("./studio-backend.js").then(({ getRuntimePresets }) => {
    return getRuntimePresets({ apiBase }).then((presets) => {
    while (mainCollapsible.content.firstChild) mainCollapsible.content.removeChild(mainCollapsible.content.firstChild);

    // Update main summary count
    var countLabel = mainCollapsible.summary.querySelector("span:last-child");
    if (countLabel) countLabel.textContent = "Presets (" + (presets ? presets.length : 0) + ")";

    // Calculate eligible axes from compared presets
    const eligible = recalcEligibleAxes(state, presets);
    state.playground._eligibleAxes = eligible;
    // Clear ineligible axes
    const axes = state.playground.experimentAxes || {};
    Object.keys(axes).forEach((ctrlId) => {
      if (!eligible.includes(ctrlId)) {
        delete axes[ctrlId];
      }
    });

    if (!presets || presets.length === 0) {
      const emptyState = document.createElement("p");
      emptyState.className = "comfymodal-studio-empty-state";
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
      emptyState.textContent = "No presets configured. ";
      emptyState.appendChild(link);
      emptyState.appendChild(document.createTextNode(" to create presets."));
      mainCollapsible.content.appendChild(emptyState);
      return;
    }

    const compareIds = (state.playground && state.playground.compareBackendIds) || [];

    // Shared render function for a single preset row
    function _renderPresetRow(b) {
      const bId = b.id || b.label || "";
      const isRunnable = b.status === "runnable" && !b.archived;
      const featureCompat = (b.compatibleFeatures || []).includes(currentFeatureId);
      const canSelect = isRunnable && featureCompat;
      let disabledReason = "";
      if (b.archived) disabledReason = "Archived";
      else if (!featureCompat) disabledReason = 'Not compatible with "' + currentFeatureId + '"';
      else if (!isRunnable && b.disabledReason) disabledReason = b.disabledReason;
      else if (!isRunnable) disabledReason = "Not runnable";

      const item = document.createElement("div");
      item.className = "comfymodal-studio-compare-item";
      if (!canSelect) item.style.opacity = "0.45";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "comfymodal-studio-compare-checkbox";
      cb.setAttribute("data-backend-id", bId);
      cb.setAttribute("data-testid", "compare-preset-" + bId);
      if (!canSelect) cb.disabled = true;
      cb.checked = canSelect && compareIds.includes(bId);
      cb.addEventListener("change", function () {
        const current = (state.playground && state.playground.compareBackendIds) || [];
        var updated;
        if (cb.checked) {
          updated = current.concat([bId]);
        } else {
          updated = current.filter(function (id) { return id !== bId; });
        }
        state.playground.compareBackendIds = updated;
        // Recalculate eligible axes and clear ineligible ones
        var eligible2 = recalcEligibleAxes(state, presets);
        state.playground._eligibleAxes = eligible2;
        var _axes = state.playground.experimentAxes || {};
        Object.keys(_axes).forEach(function (ctrlId) {
          if (!eligible2.includes(ctrlId)) {
            delete _axes[ctrlId];
          }
        });
        if (actions && actions.persistExperimentDraft) {
          actions.persistExperimentDraft();
        }
        var _matrixBody = container.parentNode
          ? container.parentNode.querySelector('[data-testid="matrix-body"]')
          : null;
        if (_matrixBody) {
          updateMatrixSummary(_matrixBody, state);
        }
        if (context && context.setPage) {
          context.setPage("playground");
        }
      });
      item.appendChild(cb);

      var label = document.createElement("span");
      label.textContent = b.label || b.id || "Unknown";
      label.style.fontSize = "var(--font-size-sm)";
      item.appendChild(label);

      if (disabledReason) {
        var reasonEl = document.createElement("span");
        reasonEl.textContent = " (" + disabledReason + ")";
        reasonEl.style.fontSize = "var(--font-size-xs)";
        reasonEl.style.color = "var(--color-text-muted)";
        reasonEl.style.marginLeft = "4px";
        item.appendChild(reasonEl);
      }

      return item;
    }

    // Group presets by their `group` field
    var grouped = _groupPresetsByField(presets);
    var groupNames = Object.keys(grouped.groups).sort(function (a, b) { return a.localeCompare(b); });

    // Render each named group as a nested collapsible
    groupNames.forEach(function (gName) {
      var groupCollapsible = _createCollapsible(gName, false, "compare-preset-group-" + gName.replace(/[^a-zA-Z0-9_-]/g, "_"));
      var gPresets = grouped.groups[gName];
      gPresets.forEach(function (bp) {
        groupCollapsible.content.appendChild(_renderPresetRow(bp));
      });
      mainCollapsible.content.appendChild(groupCollapsible.summary);
      mainCollapsible.content.appendChild(groupCollapsible.content);
    });

    // Ungrouped section (no group or empty group)
    if (grouped.ungrouped.length > 0) {
      var ungroupedCollapsible = _createCollapsible("Ungrouped", false, "compare-preset-group-ungrouped");
      grouped.ungrouped.forEach(function (bp) {
        ungroupedCollapsible.content.appendChild(_renderPresetRow(bp));
      });
      mainCollapsible.content.appendChild(ungroupedCollapsible.summary);
      mainCollapsible.content.appendChild(ungroupedCollapsible.content);
    }
    });   // end getRuntimePresets().then
  }).catch(function () {
    var errorMsg = document.createElement("p");
    errorMsg.className = "comfymodal-studio-empty-state";
    errorMsg.textContent = "Could not load presets.";
    mainCollapsible.content.appendChild(errorMsg);
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

  // Canonical preset ID set: unique([selectedBasePresetId, ...comparePresetIds])
  const canonicalPresetIds = getExperimentPresetIds(state);
  const backendCount = canonicalPresetIds.length;

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
  const eligibleAxes = (state.playground && state.playground._eligibleAxes) || [];
  const isEligible = eligibleAxes.includes(controlId);

  const wrapper = document.createElement("label");
  wrapper.className = "comfymodal-studio-axis-checkbox-wrapper";
  wrapper.setAttribute("data-testid", `axis-checkbox-${controlId}`);

  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = isAxis && isEligible;
  cb.setAttribute("data-axis", controlId);
  cb.className = "comfymodal-studio-axis-checkbox";
  cb.disabled = !isEligible;
  if (!isEligible) {
    wrapper.title = "Axis not available: not all selected presets support this control.";
  }
  cb.addEventListener("change", () => {
    if (actions && actions.toggleExperimentAxis) {
      actions.toggleExperimentAxis(controlId, cb.checked);
    }
  });

  wrapper.appendChild(cb);

  // If axis is active and eligible, insert the inline axis editor directly
  // after this control group (between this control and the next one).
  if (isAxis && isEligible) {
    const editor = renderAxisEditor(controlId, state, actions);
    if (editor) {
      // Schedule insertion after controlEl's parent processes.
      // Before inserting, remove any existing connected editor for the
      // same control to prevent duplicate editors after rapid toggling.
      setTimeout(() => {
        if (!controlEl.isConnected) return;
        const parent = controlEl.parentNode;
        const grandparent = parent;
        if (!parent || !parent.isConnected) return;
        const existingEditors = parent.querySelectorAll(`[data-testid="axis-editor-${controlId}"]`);
        for (const existing of existingEditors) {
          if (existing.isConnected) existing.remove();
        }
        grandparent.insertBefore(editor, controlEl.nextSibling);
      }, 0);
    }
  }

  return wrapper;
}

// ── Axis Editor ──────────────────────────────────────────────────────────
//
// Renders an inline axis editor for a given control. Each axis value is
// rendered as an individual input matching the original control affordance
// (number input for numeric axes, textarea for prompt/instruction axes).
// Supports add/remove of values with the first value always present.

export function renderAxisEditor(controlId, state, actions) {
  const def = CONTROL_DEFS[controlId];
  if (!def) return null;

  const editor = document.createElement("div");
  editor.className = "comfymodal-studio-axis-editor";
  editor.setAttribute("data-testid", `axis-editor-${controlId}`);

  // Values area — repeated individual value inputs
  const valuesArea = document.createElement("div");
  valuesArea.className = "comfymodal-studio-axis-editor-values";

  if (def.type === "select") {
    // Select-type axes: dropdowns populated from the backend schema options
    // when available (sampler names, scheduler names, etc.), falling back to
    // text inputs if the preset schema is not yet resolved.
    function _renderSelectValues() {
      while (valuesArea.firstChild) valuesArea.removeChild(valuesArea.firstChild);

      const axData = (state.playground && state.playground.experimentAxes && state.playground.experimentAxes[controlId]) || {};
      const vals = axData.values || [""];

      // Resolve schema options from the current preset (if available)
      const preset = state.playground && state.playground._currentPreset;
      const schema = preset && preset.controlSchemas && preset.controlSchemas[controlId];
      const options = schema && schema.options && schema.options.length > 0 ? schema.options : null;

      function collectValues() {
        const inputs = valuesArea.querySelectorAll('[data-testid^="axis-value-' + controlId + '-"]');
        return Array.from(inputs).map(function (inp) { return inp.value; });
      }

      function commitValues() {
        const v = collectValues();
        if (actions && actions.updateExperimentAxisValues) {
          actions.updateExperimentAxisValues(controlId, v);
        }
      }

      vals.forEach(function (val, i) {
        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.alignItems = "center";
        row.style.gap = "4px";
        row.style.marginBottom = "4px";

        const inputWrapper = document.createElement("div");
        inputWrapper.style.flex = "1";

        if (options) {
          // Dropdown for each axis value — respects the type of the non-experiment version
          const select = document.createElement("select");
          select.className = "comfymodal-input comfymodal-studio-select";
          select.style.fontSize = "var(--font-size-xs)";
          select.setAttribute("data-testid", "axis-value-" + controlId + "-" + i);
          options.forEach(function (optVal) {
            const opt = document.createElement("option");
            opt.value = optVal;
            opt.textContent = optVal;
            if (String(optVal) === String(val)) opt.selected = true;
            select.appendChild(opt);
          });
          select.addEventListener("change", commitValues);
          inputWrapper.appendChild(select);
        } else {
          // Fallback: text input when schema options are unavailable
          const input = document.createElement("input");
          input.type = "text";
          input.className = "comfymodal-input";
          input.style.fontSize = "var(--font-size-xs)";
          input.value = val;
          input.setAttribute("data-testid", "axis-value-" + controlId + "-" + i);
          input.addEventListener("input", commitValues);
          inputWrapper.appendChild(input);
        }

        row.appendChild(inputWrapper);

        if (i > 0) {
          const removeBtn = document.createElement("button");
          removeBtn.textContent = "\u00d7";
          removeBtn.className = "comfymodal-destructive-btn";
          removeBtn.style.fontSize = "12px";
          removeBtn.style.padding = "2px 6px";
          removeBtn.setAttribute("data-testid", "axis-remove-value-" + controlId + "-" + i);
          removeBtn.setAttribute("aria-label", "Remove value " + (i + 1));
          removeBtn.addEventListener("click", function () {
            const currentVals = collectValues();
            currentVals.splice(i, 1);
            if (actions && actions.updateExperimentAxisValues) {
              actions.updateExperimentAxisValues(controlId, currentVals);
            }
            _renderSelectValues();
          });
          row.appendChild(removeBtn);
        }

        valuesArea.appendChild(row);
      });

      // Plus button — appends a new value (first option for dropdowns, empty for text fallback)
      const addBtn = document.createElement("button");
      addBtn.textContent = "+";
      addBtn.className = "comfymodal-secondary-btn";
      addBtn.style.fontSize = "12px";
      addBtn.style.padding = "2px 8px";
      addBtn.setAttribute("data-testid", "axis-add-value-" + controlId);
      addBtn.setAttribute("aria-label", "Add value");
      addBtn.addEventListener("click", function () {
        const currentVals = collectValues();
        currentVals.push(options ? options[0] : "");
        if (actions && actions.updateExperimentAxisValues) {
          actions.updateExperimentAxisValues(controlId, currentVals);
        }
        _renderSelectValues();
      });
      valuesArea.appendChild(addBtn);
    }

    _renderSelectValues();
  } else {
    // Repeated value inputs with add/remove for experiment-eligible controls
    function _renderRepeatedValues() {
      // Clear existing children (keep the valuesArea element itself)
      while (valuesArea.firstChild) valuesArea.removeChild(valuesArea.firstChild);

      // Re-read current values from state
      const axData = (state.playground && state.playground.experimentAxes && state.playground.experimentAxes[controlId]) || {};
      const vals = axData.values || [""];

      // Collect current values from DOM inputs (live read, not stale closure)
      function collectValues() {
        const inputs = valuesArea.querySelectorAll('[data-testid^="axis-value-' + controlId + '-"]');
        return Array.from(inputs).map(function (inp) { return inp.value; });
      }

      // Commit values to state without triggering re-render
      function commitValues() {
        const v = collectValues();
        if (actions && actions.updateExperimentAxisValues) {
          actions.updateExperimentAxisValues(controlId, v);
        }
      }

      // Render each value input
      vals.forEach(function (val, i) {
        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.alignItems = "center";
        row.style.gap = "4px";
        row.style.marginBottom = "4px";

        const inputWrapper = document.createElement("div");
        inputWrapper.style.flex = "1";

        let input;
        if (def.type === "textarea") {
          input = document.createElement("textarea");
          var aeClass = "comfymodal-input comfymodal-studio-textarea";
          if (controlId === "prompt" || controlId === "negative_prompt") {
            aeClass += " comfymodal-studio-prompt-textarea";
            if (controlId === "negative_prompt") aeClass += " negative";
          }
          input.className = aeClass;
          input.rows = 2;
          input.style.fontSize = "var(--font-size-xs)";
        } else {
          // number, text, etc. — use appropriate input type
          input = document.createElement("input");
          input.type = (def.type === "number") ? "number" : "text";
          input.className = "comfymodal-input";
          input.style.fontSize = "var(--font-size-xs)";
        }

        input.value = val;
        input.setAttribute("data-testid", "axis-value-" + controlId + "-" + i);
        input.addEventListener("input", commitValues);
        inputWrapper.appendChild(input);
        row.appendChild(inputWrapper);

        // Remove button — only on values after the first (index 0 cannot be removed)
        if (i > 0) {
          const removeBtn = document.createElement("button");
          removeBtn.textContent = "\u00d7";
          removeBtn.className = "comfymodal-destructive-btn";
          removeBtn.style.fontSize = "12px";
          removeBtn.style.padding = "2px 6px";
          removeBtn.setAttribute("data-testid", "axis-remove-value-" + controlId + "-" + i);
          removeBtn.setAttribute("aria-label", "Remove value " + (i + 1));
          removeBtn.addEventListener("click", function () {
            const currentVals = collectValues();
            currentVals.splice(i, 1);
            if (actions && actions.updateExperimentAxisValues) {
              actions.updateExperimentAxisValues(controlId, currentVals);
            }
            _renderRepeatedValues();
          });
          row.appendChild(removeBtn);
        }

        valuesArea.appendChild(row);
      });

      // Plus button — appends a new value.  For seed axes the insertion
      // mode is chosen from a dropdown; all other axes keep the plain
      // empty-value append.
      const addBtn = document.createElement("button");
      addBtn.textContent = "+";
      addBtn.className = "comfymodal-secondary-btn";
      addBtn.style.fontSize = "12px";
      addBtn.style.padding = "2px 8px";
      addBtn.setAttribute("data-testid", "axis-add-value-" + controlId);
      addBtn.setAttribute("aria-label", "Add value");

      if (controlId === "seed") {
        // ── Seed: insertion dropdown adjacent to + ──────────────────
        // Modes: Increment (default), Decrement, Random (CSPRNG), Empty.
        // Increment/Decrement operate on the LAST finite seed in the list.
        // The selected mode is stored on the axis state so it persists
        // while the editor is mounted (survives value-list rebuilds and
        // page re-renders).
        const seedDef = CONTROL_DEFS.seed;
        const seedSchemaMax = (seedDef && seedDef.max != null) ? seedDef.max : 2147483647;
        const axData2 = (state.playground && state.playground.experimentAxes && state.playground.experimentAxes[controlId]) || {};
        var insertMode = axData2.insertMode || "increment";

        var seedRow = document.createElement("div");
        seedRow.style.cssText = "display:flex;align-items:center;gap:4px;margin-top:4px;";

        var modeSelect = document.createElement("select");
        modeSelect.className = "comfymodal-input comfymodal-studio-select";
        modeSelect.style.cssText = "font-size:10px;padding:2px 4px;flex:0 0 auto;";
        modeSelect.setAttribute("data-testid", "seed-insert-mode");
        modeSelect.setAttribute("aria-label", "Seed insertion mode");
        var modes = [
          { value: "increment", label: "Increment" },
          { value: "decrement", label: "Decrement" },
          { value: "random", label: "Random" },
          { value: "empty", label: "Empty" },
        ];
        modes.forEach(function (m) {
          var opt = document.createElement("option");
          opt.value = m.value;
          opt.textContent = m.label;
          modeSelect.appendChild(opt);
        });
        modeSelect.value = insertMode;
        modeSelect.addEventListener("change", function () {
          if (state.playground && state.playground.experimentAxes && state.playground.experimentAxes[controlId]) {
            state.playground.experimentAxes[controlId].insertMode = modeSelect.value;
          }
          _renderRepeatedValues();
        });
        seedRow.appendChild(modeSelect);

        var lastFinite = getLastFiniteSeed(vals);
        var boundaryMessage = "";
        if (insertMode === "increment" && lastFinite != null && lastFinite >= seedSchemaMax) {
          boundaryMessage = "Maximum seed reached";
        } else if (insertMode === "decrement" && (lastFinite == null || lastFinite <= 0)) {
          boundaryMessage = lastFinite == null ? "No finite seed to decrement" : "Minimum finite seed reached";
        }

        if (boundaryMessage) {
          var boundaryNote = document.createElement("span");
          boundaryNote.textContent = boundaryMessage;
          boundaryNote.style.cssText = "font-size:9px;color:var(--color-warning, #fbbf24);";
          boundaryNote.setAttribute("data-testid", "seed-insert-boundary");
          seedRow.appendChild(boundaryNote);
        }

        addBtn.disabled = !!boundaryMessage;
        addBtn.addEventListener("click", function () {
          var currentVals = collectValues();
          var last = getLastFiniteSeed(currentVals);
          var next;
          if (insertMode === "increment") {
            next = String((last == null ? -1 : last) + 1);
            if (Number(next) > seedSchemaMax) return;
          } else if (insertMode === "decrement") {
            if (last == null || last <= 0) return;
            next = String(last - 1);
          } else if (insertMode === "random") {
            next = String(cryptoRandomSeed(seedSchemaMax));
          } else {
            next = "";
          }
          if (!currentVals.includes(next)) {
            currentVals.push(next);
            if (actions && actions.updateExperimentAxisValues) {
              actions.updateExperimentAxisValues(controlId, currentVals);
            }
            _renderRepeatedValues();
          }
        });

        seedRow.appendChild(addBtn);
        valuesArea.appendChild(seedRow);
      } else {
        addBtn.addEventListener("click", function () {
          const currentVals = collectValues();
          currentVals.push("");
          if (actions && actions.updateExperimentAxisValues) {
            actions.updateExperimentAxisValues(controlId, currentVals);
          }
          _renderRepeatedValues();
        });
        valuesArea.appendChild(addBtn);
      }

      // ── Steps: recommended action (preset/workflow-backed) ─────────
      // Same shared source as the main control; hidden when no
      // trustworthy recommendation exists, disabled when it would be a
      // no-op for the current values.
      if (controlId === "steps") {
        var recStatus = getRecommendedStepsStatus(state, vals);
        if (recStatus.value != null) {
          var recRow = document.createElement("div");
          recRow.style.cssText = "display:flex;align-items:center;gap:4px;margin-top:4px;";
          var recBtn = document.createElement("button");
          recBtn.className = "comfymodal-secondary-btn";
          recBtn.textContent = "Use recommended (" + recStatus.value + ")";
          recBtn.style.fontSize = "10px";
          recBtn.style.padding = "2px 6px";
          recBtn.setAttribute("data-testid", "axis-steps-recommended-btn");
          if (recStatus.reason) {
            recBtn.disabled = true;
            recBtn.title = recStatus.reason;
          } else {
            recBtn.title = "From selected preset workflow capture";
            recBtn.addEventListener("click", function () {
              var currentVals = collectValues();
              if (currentVals.length === 0) {
                currentVals.push(String(recStatus.value));
              } else {
                currentVals[0] = String(recStatus.value);
                for (var _ri = currentVals.length - 1; _ri >= 1; _ri--) {
                  if (currentVals[_ri] === String(recStatus.value)) {
                    currentVals.splice(_ri, 1);
                  }
                }
              }
              if (actions && actions.updateExperimentAxisValues) {
                actions.updateExperimentAxisValues(controlId, currentVals);
              }
              _renderRepeatedValues();
            });
          }
          recRow.appendChild(recBtn);
          if (recStatus.reason) {
            var recNote = document.createElement("span");
            recNote.textContent = recStatus.reason;
            recNote.style.cssText = "font-size:9px;color:var(--color-text-muted);";
            recNote.setAttribute("data-testid", "steps-recommended-note");
            recRow.appendChild(recNote);
          }
          valuesArea.appendChild(recRow);
        }
      }
    }

    _renderRepeatedValues();
  }

  editor.appendChild(valuesArea);

  return editor;
}

// ── Run Experiment button ──────────────────────────────────────────────────
//
// Renders a "Run Experiment" button inside the experiment mode block, right
// after the Matrix Summary. This makes the run action visible alongside the
// experiment controls (Compare Presets + Matrix Summary) rather than hiding
// it at the bottom of the control panel behind all the parameter controls.
//
// The button is enabled when the experiment is valid (>= 2 presets selected,
// or 1 preset + at least 1 axis with >= 2 values, and experiments enabled
// for the current feature). Otherwise it shows a clear disabled reason inline.
//
// On click, it delegates to executeExperimentRun() and updates run state.
// Progress polling is handled by the existing renderRunButton polling loop.

export function renderExperimentRunButton(state, actions, context) {
  var container = document.createElement("div");
  container.className = "comfymodal-studio-experiment-run-section";
  container.setAttribute("data-testid", "experiment-run-section");
  container.style.marginTop = "8px";

  var runState = state.playground && state.playground.runState;
  var isRunning = runState && (
    runState.status === "running" ||
    runState.status === "submitted" ||
    runState.status === "waiting" ||
    runState.status === "queued" ||
    runState.status === "in_progress"
  );

  var btn = document.createElement("button");
  btn.className = "comfymodal-primary-btn";
  btn.setAttribute("data-testid", "run-experiment-inline-btn");

  if (isRunning) {
    btn.disabled = true;
    if (runState.status === "queued") {
      btn.textContent = "Queued\u2026";
    } else if (runState.status === "in_progress") {
      btn.textContent = "Running\u2026";
      if (runState.cellProgress) {
        btn.textContent = "Running (" + runState.cellProgress + ")\u2026";
      }
    } else {
      btn.textContent = "Running\u2026";
    }
    container.appendChild(btn);

    // Cancel button for experiment runs
    var _expApiBase = (context && context.apiBase) || "/comfymodal";
    var _cancelBtn = document.createElement("button");
    _cancelBtn.className = "comfymodal-destructive-btn";
    _cancelBtn.setAttribute("data-testid", "cancel-experiment-btn");
    _cancelBtn.textContent = runState._cancelling ? "Cancelling\u2026" : "Cancel";
    _cancelBtn.disabled = !!runState._cancelling;
    _cancelBtn.style.marginLeft = "6px";
    _cancelBtn.addEventListener("click", async function () {
      if (runState._cancelling) return;
      runState._cancelling = true;
      _cancelBtn.textContent = "Cancelling\u2026";
      _cancelBtn.disabled = true;
      // Clear any prior cancel error
      if (runState._cancelError) {
        delete runState._cancelError;
      }
      var expId = runState.experimentId || runState.runId;
      if (expId) {
        try {
          var _resp = await stopExperiment(_expApiBase, expId);
          if (!_resp || _resp.status !== "ok") {
            throw new Error((_resp && _resp.message) || "Cancel request failed");
          }
          runState._cancelling = true;
          delete runState._cancelError;
          if (actions && actions.setRunState) {
            actions.setRunState({ _cancelling: true, _cancelError: null });
          }
        } catch (e) {
          runState._cancelling = false;
          runState._cancelError = e && e.message ? e.message : "Cancel request failed";
          if (actions && actions.setRunState) {
            actions.setRunState({
              _cancelling: false,
              _cancelError: runState._cancelError,
            });
          }
        }
      } else {
        runState._cancelling = false;
        runState._cancelError = "Experiment ID unavailable";
        if (actions && actions.setRunState) {
          actions.setRunState({ _cancelling: false, _cancelError: runState._cancelError });
        }
      }
    });
    container.appendChild(_cancelBtn);
    if (runState._cancelError) {
      var _cancelErrorEl = document.createElement("p");
      _cancelErrorEl.style.cssText = "font-size:var(--font-size-sm);color:var(--color-danger);margin:4px 0 0;";
      _cancelErrorEl.textContent = runState._cancelError;
      container.appendChild(_cancelErrorEl);
    }

    return container;
  }

  if (runState && runState.status === "completed") {
    btn.disabled = false;
    btn.textContent = "Run Experiment";
    btn.title = "Run completed. Click to run again.";
    var doneMsg = document.createElement("p");
    doneMsg.style.cssText = "font-size:var(--font-size-sm);color:var(--color-success);margin:4px 0 0;";
    doneMsg.textContent = runState.completedCells
      ? "Run completed (" + runState.completedCells + " cell(s))."
      : "Run completed successfully.";
    container.appendChild(btn);
    container.appendChild(doneMsg);
    btn.onclick = buildExperimentClickHandler(state, actions, context);
    return container;
  }

  if (runState && runState.status === "error") {
    btn.disabled = false;
    btn.textContent = "Run Experiment";
    btn.title = "Run failed. Click to try again.";
    var errHeading = document.createElement("p");
    errHeading.style.cssText = "font-size:var(--font-size-sm);font-weight:var(--font-weight-semibold);color:var(--color-danger);margin:0 0 2px;";
    errHeading.textContent = "Run Failed";
    var errMsg = document.createElement("p");
    errMsg.style.cssText = "font-size:var(--font-size-sm);color:var(--color-danger);margin:0 0 4px;";
    errMsg.textContent = (runState.message || "Run failed. Try again.").substring(0, 200);
    container.appendChild(btn);
    container.appendChild(errHeading);
    container.appendChild(errMsg);
    btn.onclick = buildExperimentClickHandler(state, actions, context);
    return container;
  }

  // Determine eligibility
  var canRun = canRunExperiment(state);
  var reason = getExperimentDisabledReason(state);
  var showReason = !canRun || (reason && reason.length > 0);

  btn.textContent = "Run Experiment";
  btn.disabled = !canRun;

  if (!canRun && reason) {
    btn.title = reason;
  }

  if (canRun) {
    btn.onclick = buildExperimentClickHandler(state, actions, context);
  }

  container.appendChild(btn);

  if (showReason) {
    var reasonEl = document.createElement("p");
    reasonEl.style.cssText = "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;";
    reasonEl.textContent = reason || "";
    container.appendChild(reasonEl);
  }

  return container;
}

function buildExperimentClickHandler(state, actions, context) {
  return async function () {
    // ── Early double-submit guard (reads fresh state, survives re-render) ──
    var _preRunState = state.playground && state.playground.runState;
    if (_preRunState && (
      _preRunState.status === "running" ||
      _preRunState.status === "submitted" ||
      _preRunState.status === "waiting" ||
      _preRunState.status === "queued" ||
      _preRunState.status === "in_progress"
    )) {
      return; // Already submitting — no-op
    }

    try {
      // Update state to prevent double-submit
      var currentBtn = document.querySelector('[data-testid="run-experiment-inline-btn"]');
      if (currentBtn) {
        currentBtn.disabled = true;
        currentBtn.textContent = "Running\u2026";
      }

      // Dispose any existing scoped tracker
      var existingTracker = state.playground && state.playground._scopedTracker;
      if (existingTracker && typeof existingTracker.dispose === "function") {
        try { existingTracker.dispose(); } catch (e) {}
      }
      if (state.playground) state.playground._scopedTracker = null;

      // ── Capture config snapshot before submission ──────────────────
      // Freeze the current control values so the running panel shows
      // accurate values even if the user edits form controls while the
      // run is in flight.  Build resolved controls (CONTROL_DEFS
      // defaults → preset defaults → user edits) so every expected
      // parameter appears even when the user didn't explicitly touch it.
      var _capFeatureId = (state.playground && state.playground.featureId) || "txt2img";
      var _srcControls = (state.playground && state.playground.controls) || {};
      var _capResolved = {};
      // 1. CONTROL_DEFS defaults
      for (var _defId in CONTROL_DEFS) {
        if (Object.prototype.hasOwnProperty.call(CONTROL_DEFS, _defId)) {
          var _ctrlDef = CONTROL_DEFS[_defId];
          if (_ctrlDef.defaultValue !== undefined) {
            _capResolved[_defId] = _ctrlDef.defaultValue;
          }
        }
      }
      // 2. Preset defaults (overlay)
      var _presetForDefaults = state.playground && state.playground._currentPreset;
      var _presetDefaults = (_presetForDefaults && _presetForDefaults.defaults) || {};
      for (var _pdKey in _presetDefaults) {
        if (Object.prototype.hasOwnProperty.call(_presetDefaults, _pdKey)) {
          _capResolved[_pdKey] = _presetDefaults[_pdKey];
        }
      }
      // 3. User edits (highest priority)
      for (var _ctrlKey in _srcControls) {
        if (Object.prototype.hasOwnProperty.call(_srcControls, _ctrlKey)) {
          _capResolved[_ctrlKey] = _srcControls[_ctrlKey];
        }
      }
      var _capAxes = JSON.parse(JSON.stringify((state.playground && state.playground.experimentAxes) || {}));
      var _capPresetIds = getExperimentPresetIds(state);
      var _capPresetLabel = "";
      var _curPreset = state.playground && state.playground._currentPreset;
      if (_curPreset) {
        _capPresetLabel = _curPreset.label || _curPreset.id || "";
      }
      if (state.playground) {
        state.playground._runningExperimentConfig = {
          controls: _capResolved,
          axes: _capAxes,
          presetIds: _capPresetIds,
          presetLabel: _capPresetLabel,
          featureId: _capFeatureId,
          submittedAt: Date.now(),
        };
      }

      // Clear previous output so canvas shows live progress immediately
      if (state.playground) {
        state.playground.lastRunOutput = null;
        state.playground._selectedRun = null;
      }

      if (actions && actions.setRunState) {
        actions.setRunState({ status: "running" });
      }

      var result = await executeExperimentRun(state, context);

      if (result && result.status === "ok") {
        if (actions && actions.setRunState) {
          actions.setRunState({
            status: "submitted",
            experimentId: result.experimentId,
            message: result.message,
          });
        }

        // Create scoped tracker for this experiment's execution events
        try {
          var { createScopedTracker } = await import("./comfymodal-progress.js");
          var _expApi = (context && context.comfyApi) || (context && context.api);
          if (_expApi && typeof _expApi.addEventListener === "function") {
            var _expTracker = createScopedTracker(_expApi, {
              runId: result.experimentId,
              experimentId: result.experimentId,
              promptId: null,
            });
            if (state.playground) {
              // Dispose any existing scoped tracker first
              var _old = state.playground._scopedTracker;
              if (_old && typeof _old.dispose === "function") {
                try { _old.dispose(); } catch (e) {}
              }
              state.playground._scopedTracker = _expTracker;
            }
            _expTracker.start();
          }
        } catch (_stErr) {
          // Scoped tracker not essential — polling handles progress
        }
      } else {
        var errMsg = (result && result.message) || "Experiment run failed.";
        if (actions && actions.setRunState) {
          actions.setRunState({ status: "error", message: errMsg });
        }
      }
    } catch (_expSubmitErr) {
      // Top-level catch: any unexpected sync/async error becomes a
      // structured error state instead of an unhandled pageerror.
      if (actions && actions.setRunState) {
        actions.setRunState({
          status: "error",
          message: (_expSubmitErr && _expSubmitErr.message) || "Experiment run failed.",
        });
      }
    }
  };
}

/**
 * Check if at least one experiment axis has >= 2 values configured.
 */
function hasMultiValueAxis(state) {
  const axes = (state.playground && state.playground.experimentAxes) || {};
  return Object.values(axes).some(function (def) {
    return def && def.enabled && def.values && def.values.length >= 2;
  });
}

export function canRunExperiment(state) {
  const canonicalPresetIds = getExperimentPresetIds(state);
  if (canonicalPresetIds.length >= 2) return true;
  return canonicalPresetIds.length >= 1 && hasMultiValueAxis(state);
}

export function getExperimentDisabledReason(state) {
  const canonicalPresetIds = getExperimentPresetIds(state);
  const hasAxes = hasMultiValueAxis(state);

  if (canonicalPresetIds.length === 0) return "Select at least 2 presets (or 1 preset with a multi-value axis) to run an experiment.";
  if (canonicalPresetIds.length === 1 && !hasAxes) return "Add another preset to compare, or add at least 2 values to an experiment axis.";
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const experimentsEnabled = currentFeatureId === "txt2img";
  if (!experimentsEnabled) return "Experiments are only available for txt2img in this release.";
  return "";
}

export async function executeExperimentRun(state, context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const baseBackendId = (state.playground && state.playground.selectedBackendId) || "";
  const compareIds = (state.playground && state.playground.compareBackendIds) || [];
  const axes = (state.playground && state.playground.experimentAxes) || {};
  const controls = (state.playground && state.playground.controls) || {};

  // Canonical preset ID set: unique([selectedBasePresetId, ...comparePresetIds])
  // This ensures validation, estimation, payload, and labels all use the
  // same authoritative set.
  const allPresetIds = baseBackendId
    ? [baseBackendId].concat(compareIds.filter(function (id) { return id !== baseBackendId; }))
    : compareIds;
  const canonicalPresetIds = [...new Set(allPresetIds.filter(Boolean))];

  if (canonicalPresetIds.length === 0) {
    return { status: "error", message: "Select at least one preset to compare." };
  }

  // Build the shared experiment definition (prompts, defaults, axes).
  // Prompts and shared defaults are included ONCE — the backend applies
  // them to all presets uniformly.
  const sharedDefaults = {};
  Object.entries(controls).forEach(([key, value]) => {
    if (key !== "prompt" && key !== "negative_prompt") {
      // Parse numeric strings so backend schema validation accepts them
      sharedDefaults[key] = (typeof value === "string" && value.trim() !== "" && !isNaN(Number(value))) ? Number(value) : value;
    }
  });
  const experimentDef = {
    name: `Studio Experiment: ${currentFeatureId}`,
    defaults: sharedDefaults,
    axes: {},
    prompts: [{ text: controls.prompt || "", negative: controls.negative_prompt || "" }],
  };

  // Only submit axes that are eligible (supported by all selected presets).
  // Fix first-load/refresh race: eligibleAxes may not be populated yet if
  // renderCompareBackends hasn't completed its async getRuntimePresets call.
  // Recompute from runtime presets at submit time to guarantee accuracy.
  let eligibleAxes = (state.playground && state.playground._eligibleAxes) || [];
  var _hasEnabledAxes = false;
  for (var _ea in axes) {
    if (Object.prototype.hasOwnProperty.call(axes, _ea) && axes[_ea] && axes[_ea].enabled) {
      _hasEnabledAxes = true;
      break;
    }
  }
  if (_hasEnabledAxes && (eligibleAxes.length === 0 || Object.keys(axes).some(function (c) {
    var _a = axes[c];
    return _a && _a.enabled && !eligibleAxes.includes(c);
  }))) {
    try {
      var { listPresets } = await import("./studio-backend-api.js");
      var _allPresets = await listPresets(apiBase) || [];
      var _selPresets = canonicalPresetIds.map(function (id) {
        return _allPresets.find(function (p) { return (p.id || p.label || "") === id; });
      }).filter(Boolean);
      if (_selPresets.length > 0) {
        var recomputed = getAxisEligibilityForPresets(_selPresets, currentFeatureId);
        if (recomputed && recomputed.length > 0) {
          eligibleAxes = recomputed;
          if (state.playground) state.playground._eligibleAxes = recomputed;
        }
      }
    } catch (_eligErr) {
      // Fallback: use whatever eligibleAxes we already have
    }
  }
  Object.entries(axes).forEach(([ctrlId, def]) => {
    if (def && def.enabled && def.values && def.values.length > 0 && eligibleAxes.includes(ctrlId)) {
      var parsedValues = def.values.map(function (v) {
        if (ctrlId === "seed" && typeof v === "string" && v.trim() === "") return null;
        // Parse numeric strings so the backend schema validation
        // (which checks isinstance(value, int)) accepts them.
        if (typeof v === "string" && v.trim() !== "" && !isNaN(Number(v))) return Number(v);
        return v;
      }).filter(function (v) { return v !== null; });
      if (parsedValues.length > 0) {
        experimentDef.axes[ctrlId] = { enabled: true, values: parsedValues };
      }
    }
  });

  // Send ONE request with all presetIds — the backend creates a unified
  // experiment with one checkpoint per preset.
  const result = await runStudioExperiment(apiBase, {
    presetIds: canonicalPresetIds,
    featureId: currentFeatureId,
    experiment: experimentDef,
    metadata: { source: "studio_experiment" },
  });

  if (result && result.status === "ok") {
    return {
      status: "ok",
      experimentId: result.experimentId || "",
      count: result.cellCount || 0,
      cellCount: result.cellCount || 0,
      message: `Experiment submitted for ${canonicalPresetIds.length} preset(s) with ${result.cellCount || 0} cell(s).`,
    };
  }

  var errParts = [];
  if (result) {
    if (result.message) errParts.push(result.message);
    if (result.errors && Array.isArray(result.errors) && result.errors.length > 0) {
      result.errors.forEach(function (e) {
        if (typeof e === "string") errParts.push(e);
        else if (e && e.message) errParts.push(e.message);
      });
    }
    if (result.error) errParts.push(result.error);
    if (result.detail) errParts.push(result.detail);
  }
  return {
    status: "error",
    message: errParts.length > 0 ? errParts.join("; ") : "Experiment run failed.",
  };
}

/**
 * Compute the canonical set of preset IDs for experiment validation/display.
 * Returns a unique array derived from the base preset + compare presets.
 */
export function getExperimentPresetIds(state) {
  const baseBackendId = (state.playground && state.playground.selectedBackendId) || "";
  const compareIds = (state.playground && state.playground.compareBackendIds) || [];
  const allIds = baseBackendId
    ? [baseBackendId].concat(compareIds.filter(function (id) { return id !== baseBackendId; }))
    : compareIds;
  return [...new Set(allIds.filter(Boolean))];
}

// ── Modern Experiment V2 (D5) ────────────────────────────────────────────
//
// The modern surface submits ONE definition to POST /studio/experiment-v2
// (runExperimentV2) and owns exactly one createExperimentRunController per
// experiment.  The controller lives on state.playground._experimentController
// (never recreated on re-render); only the active experiment id is persisted
// so reopen/reload rebuilds the same fixed cell list without resubmitting.
// Legacy run/cancel rendering above is retained for existing flows.
//
// Popup close / navigation only detaches or disposes — it never cancels.

const MODERN_EXPERIMENT_ACTIVE_KEY = "comfymodal.studio.experiment.active.v1";
const MODERN_POLL_INTERVAL_MS = 3000;
const MODERN_TERMINAL_STATUSES = ["completed", "completed_with_failures", "failed", "canceled", "interrupted"];

const MODERN_EXPERIMENT_STATUS_LABELS = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  completed_with_failures: "Completed with failures",
  failed: "Failed",
  canceled: "Canceled",
  interrupted: "Interrupted",
};

/** Module-scoped context cache (apiBase + ComfyUI event bus). */
let _modernContext = { apiBase: "/comfymodal" };
/** Live modern run-section mounts; kept in sync by the controller. */
const _experimentMounts = new Set();

function _firstStr() {
  for (var i = 0; i < arguments.length; i++) {
    var v = arguments[i];
    if (v != null && String(v).trim() !== "") return String(v);
  }
  return "";
}

function _modernExperimentId() {
  var rand = "";
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      rand = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    }
  } catch (e) {}
  if (!rand) rand = Math.random().toString(36).slice(2, 14);
  return "exp_v2_" + rand;
}

/**
 * Resolve the workflow/version/preset the modern experiment should run from.
 * Values are used verbatim when state supplies them — never inferred later.
 */
export function resolveModernWorkflowSelection(state) {
  var pg = (state && state.playground) || {};
  var store = pg._workflowRun && typeof pg._workflowRun === "object" ? pg._workflowRun : {};
  var runContext = store.runContext && typeof store.runContext === "object" ? store.runContext : {};
  var workflowSnapshot = {};
  if (runContext.workflow_json && typeof runContext.workflow_json === "object") workflowSnapshot = runContext.workflow_json;
  else if (runContext.api_prompt && typeof runContext.api_prompt === "object") workflowSnapshot = runContext.api_prompt;
  else if (runContext.workflow && typeof runContext.workflow === "object") workflowSnapshot = runContext.workflow;
  return {
    workflowId: _firstStr(store.workflowId, pg.workflowId),
    workflowVersionId: _firstStr(store.workflowVersionId, pg.workflowVersionId),
    presetId: _firstStr(store.presetId, pg.workflowPresetId),
    workflowName: _firstStr(store.workflowName, pg.workflowName),
    presetName: _firstStr(store.presetName, pg.presetName),
    workflowSnapshot: workflowSnapshot,
  };
}

/** Resolve control defaults: CONTROL_DEFS → preset defaults → workflow
 * control values → explicit user edits. */
function _resolveModernControls(pg) {
  var resolved = {};
  for (var id in CONTROL_DEFS) {
    if (Object.prototype.hasOwnProperty.call(CONTROL_DEFS, id) && CONTROL_DEFS[id].defaultValue !== undefined) {
      resolved[id] = CONTROL_DEFS[id].defaultValue;
    }
  }
  var presetDefaults = (pg._currentPreset && pg._currentPreset.defaults) || {};
  for (var pk in presetDefaults) {
    if (Object.prototype.hasOwnProperty.call(presetDefaults, pk)) resolved[pk] = presetDefaults[pk];
  }
  var workflowStore = pg._workflowRun && typeof pg._workflowRun === "object" ? pg._workflowRun : {};
  var controlValues = workflowStore.controlValues || {};
  for (var ck in controlValues) {
    if (Object.prototype.hasOwnProperty.call(controlValues, ck) && controlValues[ck] != null) resolved[ck] = controlValues[ck];
  }
  var userControls = pg.controls || {};
  for (var uk in userControls) {
    if (Object.prototype.hasOwnProperty.call(userControls, uk)) resolved[uk] = userControls[uk];
  }
  return resolved;
}

/** Cartesian product of enabled axis values in fixed axis order. */
function _axisCombinations(enabledAxes) {
  var results = [];
  function walk(i, acc) {
    if (i >= enabledAxes.length) { results.push(acc); return; }
    var axis = enabledAxes[i];
    var vals = Array.isArray(axis.values) ? axis.values : [];
    if (vals.length === 0) { walk(i + 1, acc); return; }
    for (var vi = 0; vi < vals.length; vi++) {
      walk(i + 1, acc.concat([{ controlId: axis.controlId, value: vals[vi] }]));
    }
  }
  walk(0, []);
  return results;
}

/**
 * Build the fixed ordered cell list for a modern experiment definition.
 * Cells are keyed by stable cell_id (cell_0..cell_N-1) in generation order;
 * never reordered by completion.  Axis labels/values and the resolved
 * workflow/version/preset are baked per cell.
 */
export function buildModernExperimentCells(opts) {
  var o = opts && typeof opts === "object" ? opts : {};
  var experimentId = o.experimentId || "";
  var axes = Array.isArray(o.axes) ? o.axes : [];
  var selection = o.selection || {};
  var resolved = o.resolved || {};
  var basePrompt = o.prompt != null ? o.prompt : "";
  var baseNegative = o.negativePrompt != null ? o.negativePrompt : "";
  var snapshot = o.workflowSnapshot && typeof o.workflowSnapshot === "object" ? o.workflowSnapshot : {};
  var combos = _axisCombinations(axes);
  var cells = [];
  combos.forEach(function (combo, i) {
    var axisLabels = {};
    var axisValues = {};
    var controlOverrides = {};
    var promptText = basePrompt;
    var negativeText = baseNegative;
    combo.forEach(function (entry) {
      var def = CONTROL_DEFS[entry.controlId] || {};
      var label = def.label || entry.controlId;
      axisLabels[label] = String(entry.value);
      axisValues[entry.controlId] = entry.value;
      if (entry.controlId === "prompt") promptText = String(entry.value);
      else if (entry.controlId === "negative_prompt") negativeText = String(entry.value);
      else controlOverrides[entry.controlId] = entry.value;
    });
    var cellId = "cell_" + i;
    cells.push({
      cell_id: cellId,
      generation_id: "gen_" + experimentId + "_" + i,
      workflow_id: selection.workflowId || null,
      workflow_version_id: selection.workflowVersionId || null,
      preset_id: selection.presetId || null,
      axis_labels: axisLabels,
      axis_values: axisValues,
      workflow_snapshot: snapshot,
      immutable_request: {
        experiment_id: experimentId,
        cell_id: cellId,
        prompt_text: promptText,
        negative_prompt_text: negativeText,
        controls: Object.assign({}, resolved, controlOverrides),
        source: "studio_experiment_v2",
      },
    });
  });
  return cells;
}

/**
 * Build the ONE modern experiment definition from the current axes/controls
 * and resolved workflow/version/preset.  No concurrency field (the global
 * default is backend/settings-owned).  Axes are request-generation
 * convenience only.
 */
export function buildModernExperimentDefinition(state, context) {
  var pg = (state && state.playground) || {};
  var featureId = pg.featureId || "txt2img";
  var selection = resolveModernWorkflowSelection(state);
  var axes = pg.experimentAxes && typeof pg.experimentAxes === "object" ? pg.experimentAxes : {};
  var enabledAxes = Object.keys(axes)
    .filter(function (c) {
      return axes[c] && axes[c].enabled && Array.isArray(axes[c].values) && axes[c].values.length > 0;
    })
    .map(function (c) { return { controlId: c, values: axes[c].values }; });
  var resolved = _resolveModernControls(pg);
  var prompt = pg.controls && pg.controls.prompt != null ? pg.controls.prompt : (resolved.prompt != null ? resolved.prompt : "");
  var negativePrompt = pg.controls && pg.controls.negative_prompt != null
    ? pg.controls.negative_prompt
    : (resolved.negative_prompt != null ? resolved.negative_prompt : "");
  var experimentId = _modernExperimentId();
  var axisNames = enabledAxes.map(function (a) { return a.controlId; });
  var definitionAxes = {};
  enabledAxes.forEach(function (axis) {
    // The modern planner expands every definition.axes entry. Do not send
    // disabled draft axes or the client-only `enabled` flag to that seam.
    definitionAxes[axis.controlId] = { values: axis.values.slice() };
  });
  var definition = {
    name: "Studio Experiment: " + featureId,
    feature_id: featureId,
    axis_labels: { x: axisNames[0] || "", y: axisNames[1] || "" },
    axes: definitionAxes,
    defaults: resolved,
    prompts: [{ text: prompt, negative: negativePrompt }],
    workflows: selection.workflowId
      ? [{
          workflow_id: selection.workflowId,
          workflow_version_id: selection.workflowVersionId || "",
          preset_id: selection.presetId || "",
          workflow_name: selection.workflowName || "",
          preset_name: selection.presetName || "",
        }]
      : [],
  };
  if (context && context.modalOptions && typeof context.modalOptions === "object") {
    definition.modal_options = { ...context.modalOptions };
  }
  return {
    experiment_id: experimentId,
    name: definition.name,
    definition: definition,
  };
}

export function modernExperimentCanRun(state) {
  var selection = resolveModernWorkflowSelection(state);
  return !!(selection.workflowId && selection.workflowVersionId);
}

/**
 * Which experiment run surface should mount in experiment mode:
 *   - "modern": a modern Workflow/Version is selected, or an active/persisted
 *     modern experiment id exists → the D5 section (never the legacy button).
 *   - "legacy": legacy preset-only experiment flow (existing renderer).
 */
export function experimentRunSurface(state) {
  if (modernExperimentCanRun(state)) return "modern";
  var pg = state && state.playground;
  if (pg && pg._activeExperimentId) return "modern";
  try {
    if (loadActiveExperimentId()) return "modern";
  } catch (e) { /* ignore */ }
  return "legacy";
}

export function modernExperimentDisabledReason(state) {
  var selection = resolveModernWorkflowSelection(state);
  if (!selection.workflowId) return "Select a Workflow and Version to run a modern experiment.";
  if (!selection.workflowVersionId) return "Select a Workflow Version to run a modern experiment.";
  return "";
}

/** Canonical status label for chips; canceled/interrupted/failed distinct. */
export function experimentStatusLabel(status) {
  return MODERN_EXPERIMENT_STATUS_LABELS[status]
    || (status != null ? String(status) : "Queued");
}

export function isTerminalModernStatus(status) {
  return MODERN_TERMINAL_STATUSES.indexOf(status) !== -1;
}

export function canResumeModernExperiment(status, cells) {
  // Only an actively RUNNING experiment suppresses Resume.  A "queued"
  // aggregate with queued/not-started cells IS resume-eligible; failed cells
  // are never resumed (they require per-cell Retry).
  if (status === "running") return false;
  return (Array.isArray(cells) ? cells : []).some(function (c) {
    return c && (c.status === "interrupted" || c.status === "queued");
  });
}

export function getResumeEligibleCellCount(status, cells) {
  if (!canResumeModernExperiment(status, cells)) return 0;
  return (Array.isArray(cells) ? cells : []).reduce(function (n, c) {
    return n + (c && (c.status === "interrupted" || c.status === "queued") ? 1 : 0);
  }, 0);
}

export function canRetryModernCell(cell) {
  return !!(cell && cell.status === "failed");
}

// ── Active experiment id persistence (reload/reopen) ─────────────────────

export function loadActiveExperimentId() {
  try {
    var raw = localStorage.getItem(MODERN_EXPERIMENT_ACTIVE_KEY);
    if (raw) {
      var parsed = JSON.parse(raw);
      if (parsed && typeof parsed.experimentId === "string" && parsed.experimentId) {
        return parsed.experimentId;
      }
    }
  } catch (e) { /* ignore */ }
  return "";
}

export function persistActiveExperimentId(experimentId) {
  try {
    if (experimentId) {
      localStorage.setItem(MODERN_EXPERIMENT_ACTIVE_KEY, JSON.stringify({ experimentId: String(experimentId) }));
    } else {
      localStorage.removeItem(MODERN_EXPERIMENT_ACTIVE_KEY);
    }
  } catch (e) { /* ignore */ }
}

export function clearActiveExperimentId() {
  persistActiveExperimentId("");
}

// ── Controller lifecycle ─────────────────────────────────────────────────

/**
 * Get the ONE per-experiment controller, creating it once.  Re-render never
 * creates a second controller.  Returns null when no active experiment id.
 */
export function getModernExperimentController(state, context) {
  var pg = state && state.playground;
  if (!pg) return null;
  var ctx = context || _modernContext;
  var apiBase = (ctx && ctx.apiBase) || "/comfymodal";
  var id = pg._activeExperimentId || "";
  if (!id) return null;
  var existing = pg._experimentController;
  if (existing && String(existing.getExperimentId()) === id) return existing;
  if (existing && typeof existing.dispose === "function") {
    try { existing.dispose(); } catch (e) {}
  }
  pg._experimentController = null;
  var controller = createExperimentRunController({
    experimentId: id,
    apiBase: apiBase,
    actions: {
      cancel: (eid) => cancelExperimentV2(apiBase, eid),
      resume: (eid) => resumeExperiment(apiBase, eid),
      retryCell: (eid, cellId) => retryCell(apiBase, eid, cellId),
    },
  });
  controller.subscribe(function () { _updateExperimentSectionMounts(state); });
  pg._experimentController = controller;
  return controller;
}

/**
 * Fetch the modern status endpoint and reconcile the controller.  The status
 * response wraps detail under `item`; the controller consumes the unwrapped
 * payload.
 */
export async function refreshModernExperimentStatus(state, context) {
  var ctx = context || _modernContext;
  var pg = state && state.playground;
  var experimentId = pg && pg._activeExperimentId;
  if (!experimentId) return null;
  var apiBase = (ctx && ctx.apiBase) || "/comfymodal";
  var controller = getModernExperimentController(state, ctx);
  if (!controller) return null;
  try {
    var data = await getExperimentV2Status(apiBase, experimentId);
    var payload = data && data.item && typeof data.item === "object" ? data.item : data;
    if (payload && typeof payload === "object") controller.reconcile(payload);
    return payload;
  } catch (e) {
    return null;
  }
}

export function stopModernExperimentPolling(state) {
  var pg = state && state.playground;
  if (pg && pg._experimentPollTimer != null) {
    clearInterval(pg._experimentPollTimer);
    pg._experimentPollTimer = null;
  }
}

export function startModernExperimentPolling(state, context) {
  stopModernExperimentPolling(state);
  var ctx = context || _modernContext;
  var pg = state && state.playground;
  if (!pg || !pg._activeExperimentId) return;
  var apiBase = (ctx && ctx.apiBase) || "/comfymodal";
  var timer = setInterval(async function () {
    var s = state && state.playground;
    if (!s || !s._activeExperimentId || state.activePage !== "playground") {
      stopModernExperimentPolling(state);
      return;
    }
    var controller = getModernExperimentController(state, ctx);
    if (!controller) { stopModernExperimentPolling(state); return; }
    try {
      var data = await getExperimentV2Status(apiBase, s._activeExperimentId);
      var payload = data && data.item && typeof data.item === "object" ? data.item : data;
      if (payload && typeof payload === "object") controller.reconcile(payload);
      var st = controller.getState();
      if (isTerminalModernStatus(st.status)) stopModernExperimentPolling(state);
    } catch (e) { /* transient poll error — keep polling */ }
  }, MODERN_POLL_INTERVAL_MS);
  if (state && state.playground) state.playground._experimentPollTimer = timer;
}

/**
 * Attach the controller to the existing ComfyUI event source (if available)
 * and start modern status polling.  Reopen/reload with an existing id rebuilds
 * the same fixed cell list without submitting again.
 */
export function attachModernExperiment(state, actions, context) {
  var ctx = context || _modernContext;
  if (context) _modernContext = context;
  var pg = state && state.playground;
  var experimentId = pg && pg._activeExperimentId;
  if (!experimentId) return null;
  var controller = getModernExperimentController(state, ctx);
  if (!controller) return null;
  var source = (ctx && ctx.comfyApi) || (ctx && ctx.api);
  controller.attach(source);
  startModernExperimentPolling(state, ctx);
  refreshModernExperimentStatus(state, ctx);
  return controller;
}

/**
 * Popup close / navigation: only detach the event source, stop polling and
 * drop mounts.  Never cancels the experiment.
 */
export function detachModernExperiment(state, actions) {
  stopModernExperimentPolling(state);
  var pg = state && state.playground;
  var controller = pg && pg._experimentController;
  if (controller && typeof controller.detachEventSource === "function") {
    try { controller.detachEventSource(); } catch (e) {}
  }
  _experimentMounts.clear();
  return controller;
}

/** Full dispose (still never cancels). */
export function disposeModernExperiment(state, actions) {
  stopModernExperimentPolling(state);
  var pg = state && state.playground;
  var controller = pg && pg._experimentController;
  if (controller && typeof controller.dispose === "function") {
    try { controller.dispose(); } catch (e) {}
  }
  if (pg) pg._experimentController = null;
  _experimentMounts.clear();
}

/**
 * Submit exactly one modern definition via runExperimentV2.  Guarded against
 * double-submit while an experiment is active.
 */
export async function executeModernExperimentRun(state, actions, context) {
  var pg = state && state.playground;
  if (!pg) return { status: "error", message: "Playground state unavailable." };
  var ctx = context || _modernContext;
  var existing = pg._experimentController;
  if (existing) {
    var st = existing.getState();
    if (st.status === "running" || st.status === "queued") {
      return { status: "ok", guarded: true, message: "Experiment already active." };
    }
  }
  var apiBase = (ctx && ctx.apiBase) || "/comfymodal";
  var modalOptions = await loadModalOptions(apiBase);
  var payload = buildModernExperimentDefinition(state, Object.assign({}, ctx || {}, {
    modalOptions: modalOptions,
  }));
  var result;
  try {
    result = await runExperimentV2(apiBase, payload);
  } catch (e) {
    return { status: "error", message: (e && e.message) || "Experiment submission failed." };
  }
  if (!result || result.status !== "ok" || !result.experiment_id) {
    return {
      status: "error",
      message: (result && (result.message || result.detail)) || "Experiment submission failed.",
    };
  }
  var experimentId = result.experiment_id;
  pg._activeExperimentId = experimentId;
  persistActiveExperimentId(experimentId);
  var controller = getModernExperimentController(state, ctx);
  if (controller && result.item && typeof result.item === "object") {
    controller.reconcile(result.item);
  }
  attachModernExperiment(state, actions, ctx);
  return {
    status: "ok",
    experimentId: experimentId,
    cellCount: (result.item && result.item.total) || result.total || 0,
  };
}

// ── Modern run section rendering ─────────────────────────────────────────

function _mountSignature(st) {
  if (!st) return "";
  return [
    st.status || "",
    st.total || 0,
    JSON.stringify(st.counts || {}),
    (Array.isArray(st.cells) ? st.cells : []).map(function (c) {
      return (c.cellId || "") + ":" + (c.status || "") + ":" + (c.thumbUrl ? "t" : "-")
        + ":" + (c.attemptId || "") + ":" + (c.error ? "e" : "-");
    }).join("|"),
  ].join("~");
}

function _updateExperimentSectionMounts(state) {
  var pg = state && state.playground;
  if (!pg) return;
  Array.from(_experimentMounts).forEach(function (mount) {
    if (!mount.isConnected) { _experimentMounts.delete(mount); return; }
    try { _syncExperimentMount(mount, state); } catch (e) { /* isolated */ }
  });
}

export function renderModernCellTile(cell, index, state, actions, context) {
  var ctx = context || _modernContext;
  var cellId = (cell && cell.cellId) || "cell_" + index;
  var status = (cell && cell.status) || "queued";
  var tile = document.createElement("div");
  tile.className = "comfymodal-studio-experiment-v2-cell " + status;
  tile.setAttribute("data-testid", "experiment-v2-cell-" + cellId);
  tile.setAttribute("data-cell-id", cellId);
  tile.setAttribute("data-cell-status", status);

  if (cell && cell.thumbUrl) {
    var img = document.createElement("img");
    img.className = "comfymodal-studio-experiment-v2-cell-thumb";
    img.src = cell.thumbUrl;
    img.alt = "Cell " + cellId;
    img.loading = "lazy";
    tile.appendChild(img);
  } else {
    var empty = document.createElement("div");
    empty.className = "comfymodal-studio-experiment-v2-cell-empty";
    empty.textContent = status === "queued" ? "Queued" : "No image";
    tile.appendChild(empty);
  }

  var chip = document.createElement("span");
  chip.className = "comfymodal-studio-history-v2-chip status-" + status;
  chip.textContent = experimentStatusLabel(status);
  tile.appendChild(chip);

  var meta = document.createElement("div");
  meta.className = "comfymodal-studio-experiment-v2-cell-meta";
  meta.textContent = modernCellMetaText(cell) || "Cell " + cellId;
  tile.appendChild(meta);

  // Sampler and workflow progress stay in separate slots.
  if (cell && cell.sampler && cell.sampler.step != null) {
    var samp = document.createElement("div");
    samp.className = "comfymodal-studio-experiment-v2-cell-sampler";
    samp.setAttribute("data-testid", "experiment-v2-cell-sampler-" + cellId);
    var sampMax = cell.sampler.max != null ? cell.sampler.max : "?";
    samp.textContent = "Sampling " + cell.sampler.step + "/" + sampMax;
    tile.appendChild(samp);
  }
  if (cell && cell.progress && cell.progress.completedNodes != null) {
    var prog = document.createElement("div");
    prog.className = "comfymodal-studio-experiment-v2-cell-workflow";
    prog.setAttribute("data-testid", "experiment-v2-cell-workflow-" + cellId);
    var progTotal = cell.progress.totalNodes != null ? cell.progress.totalNodes : "?";
    prog.textContent = "Workflow " + cell.progress.completedNodes + "/" + progTotal;
    tile.appendChild(prog);
  }

  if (canRetryModernCell(cell)) {
    var retryBtn = document.createElement("button");
    retryBtn.className = "comfymodal-secondary-btn";
    retryBtn.setAttribute("data-testid", "experiment-v2-cell-retry-" + cellId);
    retryBtn.textContent = "Retry";
    retryBtn.addEventListener("click", function () {
      if (retryBtn.disabled) return;
      var ctrl = getModernExperimentController(state, ctx);
      if (!ctrl) return;
      retryBtn.disabled = true;
      retryBtn.textContent = "Retrying\u2026";
      ctrl.retryCell(cellId).then(function () {
        refreshModernExperimentStatus(state, ctx);
      });
    });
    tile.appendChild(retryBtn);
  }

  if (cell && cell.error) {
    var err = document.createElement("div");
    err.className = "comfymodal-studio-experiment-v2-cell-error";
    err.textContent = String(cell.error).substring(0, 120);
    tile.appendChild(err);
  }

  return tile;
}

export function modernCellMetaText(cell) {
  if (!cell || typeof cell !== "object") return "";
  var parts = [];
  // Prefer resolved names (workflow_name/preset_name) over raw ids; ids are
  // the fallback when the status endpoint only supplies them.
  var wfName = cell.workflowName || cell.workflowId || "";
  var wfVersion = cell.workflowVersionId || "";
  var presetName = cell.presetName || cell.presetId || "";
  var wfParts = [wfName, wfVersion, presetName].filter(Boolean);
  if (wfParts.length > 0) parts.push(wfParts.join(" \u00b7 "));
  return parts.join(" \u00b7 ");
}

function _renderModernGridInto(gridEl, cells, state, actions, context) {
  (Array.isArray(cells) ? cells : []).forEach(function (cell, index) {
    gridEl.appendChild(renderModernCellTile(cell, index, state, actions, context));
  });
}

function _syncExperimentMount(mount, state) {
  var pg = state && state.playground;
  var experimentId = pg && pg._activeExperimentId ? pg._activeExperimentId : "";
  var controller = pg && pg._experimentController;
  var st = controller ? controller.getState() : null;
  var sig = _mountSignature(st);
  if (mount._experimentSignature === sig && mount._experimentId === experimentId) return;
  mount._experimentSignature = sig;
  mount._experimentId = experimentId;

  var hasActive = !!experimentId;

  var submitBtn = mount.querySelector('[data-testid="modern-experiment-submit-btn"]');
  var reasonEl = mount.querySelector('[data-testid="modern-experiment-reason"]');
  if (submitBtn) {
    var active = st && (st.status === "running" || st.status === "queued");
    if (active) {
      submitBtn.disabled = true;
      submitBtn.textContent = st.status === "queued" ? "Queued\u2026" : "Running\u2026";
      if (reasonEl) reasonEl.textContent = "";
    } else {
      var canRun = modernExperimentCanRun(state);
      submitBtn.disabled = !canRun;
      submitBtn.textContent = "Run Experiment";
      if (reasonEl) reasonEl.textContent = canRun ? "" : modernExperimentDisabledReason(state);
    }
  }

  var progressEl = mount.querySelector('[data-testid="experiment-v2-progress"]');
  if (progressEl) {
    if (hasActive && st) {
      progressEl.style.display = "";
      progressEl.textContent = formatExperimentProgress(st.counts, st.total);
    } else {
      progressEl.style.display = "none";
      progressEl.textContent = "";
    }
  }

  var gridEl = mount.querySelector('[data-testid="experiment-v2-grid"]');
  if (gridEl) {
    while (gridEl.firstChild) gridEl.removeChild(gridEl.firstChild);
    if (hasActive && st) {
      gridEl.style.display = "";
      _renderModernGridInto(gridEl, st.cells, state, null, _modernContext);
    } else {
      gridEl.style.display = "none";
    }
  }

  var cancelBtn = mount.querySelector('[data-testid="modern-experiment-cancel-btn"]');
  var resumeBtn = mount.querySelector('[data-testid="modern-experiment-resume-btn"]');
  var actionNote = mount.querySelector('[data-testid="experiment-v2-action-note"]');
  if (cancelBtn) {
    var cancellable = st && (st.status === "running" || st.status === "queued");
    cancelBtn.style.display = hasActive && cancellable ? "" : "none";
    cancelBtn.disabled = false;
    cancelBtn.textContent = "Cancel";
  }
  if (resumeBtn) {
    var eligible = hasActive && st && canResumeModernExperiment(st.status, st.cells);
    resumeBtn.style.display = eligible ? "" : "none";
    resumeBtn.disabled = false;
    resumeBtn.textContent = "Resume";
  }
  if (actionNote) actionNote.textContent = "";
}

export function renderModernExperimentSection(state, actions, context) {
  var ctx = context || _modernContext;
  if (context) _modernContext = context;

  var container = document.createElement("div");
  container.className = "comfymodal-studio-experiment-v2-section";
  container.setAttribute("data-testid", "experiment-v2-section");

  var heading = document.createElement("h4");
  heading.className = "comfymodal-studio-block-heading";
  heading.textContent = "Experiment Run (V2)";
  container.appendChild(heading);

  var submitRow = document.createElement("div");
  submitRow.className = "comfymodal-studio-experiment-v2-run-row";

  var submitBtn = document.createElement("button");
  submitBtn.className = "comfymodal-primary-btn";
  submitBtn.setAttribute("data-testid", "modern-experiment-submit-btn");
  submitBtn.textContent = "Run Experiment";
  submitBtn.addEventListener("click", function () {
    if (submitBtn.disabled) return;
    submitBtn.disabled = true;
    submitBtn.textContent = "Running\u2026";
    executeModernExperimentRun(state, actions, ctx).then(function (result) {
      if (result && result.status !== "ok" && actions && actions.setRunState) {
        actions.setRunState({ status: "error", message: result.message || "Experiment submission failed." });
      }
    });
  });
  submitRow.appendChild(submitBtn);

  var reasonEl = document.createElement("p");
  reasonEl.className = "comfymodal-studio-experiment-v2-reason";
  reasonEl.setAttribute("data-testid", "modern-experiment-reason");
  reasonEl.style.fontSize = "var(--font-size-sm)";
  reasonEl.style.color = "var(--color-text-secondary)";
  reasonEl.style.margin = "4px 0 0";
  submitRow.appendChild(reasonEl);
  container.appendChild(submitRow);

  var progressEl = document.createElement("div");
  progressEl.className = "comfymodal-studio-experiment-v2-progress";
  progressEl.setAttribute("data-testid", "experiment-v2-progress");
  progressEl.setAttribute("aria-live", "polite");
  container.appendChild(progressEl);

  var gridEl = document.createElement("div");
  gridEl.className = "comfymodal-studio-experiment-v2-grid";
  gridEl.setAttribute("data-testid", "experiment-v2-grid");
  container.appendChild(gridEl);

  var actionRow = document.createElement("div");
  actionRow.className = "comfymodal-studio-experiment-v2-actions";

  var cancelBtn = document.createElement("button");
  cancelBtn.className = "comfymodal-destructive-btn";
  cancelBtn.setAttribute("data-testid", "modern-experiment-cancel-btn");
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", function () {
    if (cancelBtn.disabled) return;
    var ctrl = getModernExperimentController(state, ctx);
    if (!ctrl) return;
    cancelBtn.disabled = true;
    cancelBtn.textContent = "Cancelling\u2026";
    ctrl.cancel().then(function () {
      cancelBtn.disabled = false;
      cancelBtn.textContent = "Cancel";
      refreshModernExperimentStatus(state, ctx);
    });
  });
  actionRow.appendChild(cancelBtn);

  var resumeBtn = document.createElement("button");
  resumeBtn.className = "comfymodal-secondary-btn";
  resumeBtn.setAttribute("data-testid", "modern-experiment-resume-btn");
  resumeBtn.textContent = "Resume";
  resumeBtn.addEventListener("click", function () {
    if (resumeBtn.disabled) return;
    var ctrl = getModernExperimentController(state, ctx);
    if (!ctrl) return;
    resumeBtn.disabled = true;
    resumeBtn.textContent = "Resuming\u2026";
    ctrl.resume().then(function () {
      resumeBtn.disabled = false;
      resumeBtn.textContent = "Resume";
      refreshModernExperimentStatus(state, ctx);
    });
  });
  actionRow.appendChild(resumeBtn);

  var actionNote = document.createElement("span");
  actionNote.className = "comfymodal-studio-history-v2-action-note";
  actionNote.setAttribute("data-testid", "experiment-v2-action-note");
  actionNote.setAttribute("aria-live", "polite");
  actionRow.appendChild(actionNote);
  container.appendChild(actionRow);

  _experimentMounts.add(container);

  // Reopen/reload with an existing id: rebuild the same fixed cell list and
  // reattach without submitting again.
  var pg = state && state.playground;
  if (pg && !pg._activeExperimentId) {
    var persistedId = loadActiveExperimentId();
    if (persistedId) pg._activeExperimentId = persistedId;
  }
  attachModernExperiment(state, actions, ctx);
  _syncExperimentMount(container, state);
  return container;
}

// ── Full experiment mode renderer ────────────────────────────────────────

let _experimentSurfaceWatcher = null;
let _experimentSurfaceHost = null;

/**
 * Mount exactly ONE run surface into the host:
 *   - "modern"  → the D5 section (runExperimentV2 + controller, fixed grid,
 *                 no concurrency payload). The legacy button is NOT mounted.
 *   - "legacy"  → the existing legacy experiment run renderer/visual layout.
 * Workflow/Version selection does not re-render the control panel, so a small
 * self-clearing watcher swaps the surface when the state flips (no double
 * submit buttons in either state).
 */
function _mountExperimentRunSurface(host, state, actions, context) {
  var surface = experimentRunSurface(state);
  if (host._experimentSurface === surface) return;
  host._experimentSurface = surface;
  while (host.firstChild) host.removeChild(host.firstChild);
  if (surface === "modern") {
    host.appendChild(renderModernExperimentSection(state, actions, context || {}));
  } else {
    host.appendChild(renderExperimentRunButton(state, actions, context));
  }
}

export function renderExperimentMode(state, actions, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-experiment-mode";
  container.setAttribute("data-testid", "experiment-mode");

  // Compare Backends block (context passed explicitly)
  container.appendChild(renderCompareBackends(state, actions, context || {}));

  // Matrix Summary block
  container.appendChild(renderMatrixSummary(state, actions));

  // Exactly one run surface (legacy preset flow OR the modern V2 section) —
  // never two experiment submit buttons for modern state.
  const surfaceHost = document.createElement("div");
  surfaceHost.className = "comfymodal-studio-experiment-run-surface";
  surfaceHost.setAttribute("data-testid", "experiment-run-surface");
  container.appendChild(surfaceHost);

  _mountExperimentRunSurface(surfaceHost, state, actions, context || {});

  // Workflow/Version selection updates state without re-rendering the control
  // panel, so re-evaluate the surface until the host detaches.
  if (_experimentSurfaceWatcher) {
    clearInterval(_experimentSurfaceWatcher);
    _experimentSurfaceWatcher = null;
  }
  _experimentSurfaceHost = surfaceHost;
  _experimentSurfaceWatcher = setInterval(function () {
    const host = _experimentSurfaceHost;
    if (!host || !host.isConnected) {
      // Playground navigation / popup close: detach the modern controller
      // (event listeners + polling) without cancelling, preserving the
      // controller and active experiment id for reopen.  Never dispose here —
      // only the explicit disposeModernExperiment does that.
      detachModernExperiment(state, actions);
      clearInterval(_experimentSurfaceWatcher);
      _experimentSurfaceWatcher = null;
      _experimentSurfaceHost = null;
      return;
    }
    _mountExperimentRunSurface(host, state, actions, context || {});
  }, 1200);

  // Reset to Default button — resets all experiment controls and axes to preset defaults
  if (actions && actions.resetToDefaults) {
    var resetBtn = document.createElement("button");
    resetBtn.className = "comfymodal-secondary-btn";
    resetBtn.textContent = "Reset to Default";
    resetBtn.setAttribute("data-testid", "reset-to-default-btn");
    resetBtn.setAttribute("aria-label", "Reset all experiment controls to their default values");
    resetBtn.addEventListener("click", function () {
      actions.resetToDefaults();
    });
    container.appendChild(resetBtn);
  }

  return container;
}
