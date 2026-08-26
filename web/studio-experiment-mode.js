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
import { renderEmptyState } from "./studio-ui.js";

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
      // Phase I8: ordinary empty state via the shared primitive; frozen
      // wording "Open Backend to create presets" applies here too.
      const link = document.createElement("a");
      link.href = "#";
      link.textContent = "Open Backend to create presets.";
      link.style.color = "var(--color-accent)";
      link.style.cursor = "pointer";
      link.addEventListener("click", (e) => {
        e.preventDefault();
        if (actions && actions.navigateToBackendTab) {
          actions.navigateToBackendTab();
        }
      });
      const emptyState = renderEmptyState({
        title: "No presets configured.",
        action: link,
        testid: "experiment-presets-empty",
      });
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
    // Phase I8: no-selection hint via the shared empty-state primitive
    // (the warning paragraph below stays a truthful status note).
    body.appendChild(renderEmptyState({
      title: "Check boxes next to controls to add them as experiment axes.",
      testid: "experiment-matrix-empty",
    }));

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
// H-WAVE D: the active-legacy run/cancel renderer was retired; this V2
// section is the only experiment surface.
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
 *   - "modern": the D5 section — mounted for every state.  When no modern
 *     Workflow/Version identity exists the section mounts GATED, with Run
 *     disabled and a visible reason.
 *   H-WAVE D: the active-legacy view/control surface ("legacy") is retired;
 *   there is no other surface.
 */
export function experimentRunSurface(state) {
  // H-WAVE D: the active-legacy view/control surface is retired.
  // Every state mounts the modern (possibly gated) experiment-v2 section.
  void state;
  return "modern";
}

export function modernExperimentDisabledReason(state) {
  var selection = resolveModernWorkflowSelection(state);
  if (!selection.workflowId) return "Select a Workflow and Version before running an experiment.";
  if (!selection.workflowVersionId) return "Select a Workflow Version before running an experiment.";
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
  // H-WAVE A4: fail closed without modern identity.  No legacy creator, no
  // synthesized WorkflowVersion, no V1 fallback — the run action is gated
  // truthfully in the UI and refused here as a backstop.
  if (!modernExperimentCanRun(state)) {
    return {
      status: "error",
      gated: true,
      message: modernExperimentDisabledReason(state) || "Select a Workflow and Version before running an experiment.",
    };
  }
  var ctx = context || _modernContext;
  var existing = pg._experimentController;
  if (existing) {
    var st = existing.getState();
    if (st.status === "running" || st.status === "queued") {
      return { status: "ok", guarded: true, message: "Experiment already active." };
    }
  }
  // Rapid-click dedupe: one submission in flight at a time, independent of
  // controller state (which only exists after the first submission resolves).
  if (pg._experimentSubmitInFlight) {
    return { status: "ok", guarded: true, message: "Experiment submission already in progress." };
  }
  pg._experimentSubmitInFlight = true;
  var apiBase = (ctx && ctx.apiBase) || "/comfymodal";
  try {
    return await _submitModernExperimentRun(state, pg, actions, ctx, apiBase);
  } finally {
    pg._experimentSubmitInFlight = false;
  }
}

async function _submitModernExperimentRun(state, pg, actions, ctx, apiBase) {
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

function _mountSignature(st, state) {
  // The gating state (modern Workflow/Version identity) participates in the
  // signature so selecting/deselecting a workflow re-syncs the mounted
  // section's Run button and reason without a full surface remount.
  var gate = state && modernExperimentCanRun(state) ? "run-ok" : "gated";
  if (!st) return gate;
  return [
    gate,
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

/** Truthful shared-chip tone for a canonical experiment status (Phase I8). */
function _cellStatusTone(status) {
  if (status === "completed") return "ok";
  if (status === "completed_with_failures" || status === "interrupted") return "warn";
  if (status === "failed") return "error";
  if (status === "running" || status === "queued" || status === "pending") return "running";
  return "neutral";
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

  // Phase I8: cell status chip adopts the shared cm-chip base + truthful
  // data-tone; the legacy family class (and its ::before dot) is preserved.
  var chip = document.createElement("span");
  chip.className = "comfymodal-studio-history-v2-chip status-" + status + " cm-chip";
  chip.setAttribute("data-tone", _cellStatusTone(status));
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
  var sig = _mountSignature(st, state);
  if (mount._experimentSignature === sig && mount._experimentId === experimentId) return;
  mount._experimentSignature = sig;
  mount._experimentId = experimentId;

  var hasActive = !!experimentId;

  var submitBtn = mount.querySelector('[data-testid="modern-experiment-submit-btn"]');
  var reasonEl = mount.querySelector('[data-testid="modern-experiment-reason"]');
  var wfLink = mount.querySelector('[data-testid="modern-experiment-workflows-link"]');
  if (submitBtn) {
    var active = st && (st.status === "running" || st.status === "queued");
    if (active) {
      submitBtn.disabled = true;
      submitBtn.textContent = st.status === "queued" ? "Queued\u2026" : "Running\u2026";
      if (reasonEl) reasonEl.textContent = "";
      if (wfLink) wfLink.style.display = "none";
    } else {
      var canRun = modernExperimentCanRun(state);
      submitBtn.disabled = !canRun;
      submitBtn.textContent = "Run Experiment";
      if (reasonEl) reasonEl.textContent = canRun ? "" : modernExperimentDisabledReason(state);
      if (wfLink) wfLink.style.display = canRun ? "none" : "";
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

  // Existing contextual route to the Workflows owner (no new deep-link infra):
  // same navigation the workflow gating line already offers.
  if (ctx && typeof ctx.setPage === "function") {
    var wfLink = document.createElement("a");
    wfLink.className = "comfymodal-studio-experiment-v2-workflows-link";
    wfLink.setAttribute("data-testid", "modern-experiment-workflows-link");
    wfLink.textContent = "Open Workflows";
    wfLink.href = "#";
    wfLink.style.cssText = "font-size:var(--font-size-sm);color:var(--color-accent);cursor:pointer;margin-left:6px;";
    wfLink.addEventListener("click", function (e) {
      e.preventDefault();
      ctx.setPage("workflows");
    });
    submitRow.appendChild(wfLink);
  }
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
 * Mount exactly ONE run surface into the host: the modern D5 section
 * (runExperimentV2 + controller, fixed grid, no concurrency payload).  It is
 * mounted for valid modern identity, active/persisted modern experiments, AND
 * as the gated default when identity is missing (H-WAVE A4).  H-WAVE D: the
 * active-legacy view/control surface is retired — there is no other surface.
 * Workflow/Version selection does not re-render the control panel, so a small
 * self-clearing watcher re-syncs the modern section's gating via its mount
 * signature.
 */
function _mountExperimentRunSurface(host, state, actions, context) {
  host._experimentSurface = "modern";
  while (host.firstChild) host.removeChild(host.firstChild);
  host.appendChild(renderModernExperimentSection(state, actions, context || {}));
}

export function renderExperimentMode(state, actions, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-experiment-mode";
  container.setAttribute("data-testid", "experiment-mode");

  // Compare Backends block (context passed explicitly)
  container.appendChild(renderCompareBackends(state, actions, context || {}));

  // Matrix Summary block
  container.appendChild(renderMatrixSummary(state, actions));

  // Exactly one run surface: the modern V2 section (gated when modern
  // identity is missing — H-WAVE A4 fallback closure).  H-WAVE D: the
  // active-legacy view/control surface is retired.
  const surfaceHost = document.createElement("div");
  surfaceHost.className = "comfymodal-studio-experiment-run-surface";
  surfaceHost.setAttribute("data-testid", "experiment-run-surface");
  container.appendChild(surfaceHost);

  _mountExperimentRunSurface(surfaceHost, state, actions, context || {});

  // Workflow/Version selection updates state without re-rendering the control
  // panel, so re-sync the mounted modern section's gating until the host
  // detaches.
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
