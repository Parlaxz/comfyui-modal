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
import { getRuntimePresets } from "./studio-backend.js";
import { runStudioExperiment } from "./studio-backend-api.js";
import { getAxisEligibilityForPresets } from "./studio-preset-capabilities.js";

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

// ── Compare Backends block ───────────────────────────────────────────────

export function renderCompareBackends(state, actions, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-compare-backends";
  container.setAttribute("data-testid", "compare-backends");

  const heading = document.createElement("h4");
  heading.className = "comfymodal-studio-block-heading";
  heading.textContent = "Compare Presets";
  container.appendChild(heading);

  const list = document.createElement("div");
  list.className = "comfymodal-studio-compare-list";
  container.appendChild(list);

  const apiBase = (context && context.apiBase) || "/comfymodal";
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";

  getRuntimePresets({ apiBase }).then((presets) => {
    while (list.firstChild) list.removeChild(list.firstChild);

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
      list.appendChild(emptyState);
      return;
    }

    const compareIds = (state.playground && state.playground.compareBackendIds) || [];

    presets.forEach((b) => {
      const bId = b.id || b.label || "";
      const isRunnable = b.status === "runnable" && !b.archived;
      const featureCompat = (b.compatibleFeatures || []).includes(currentFeatureId);
      const canSelect = isRunnable && featureCompat;
      let disabledReason = "";
      if (b.archived) disabledReason = "Archived";
      else if (!featureCompat) disabledReason = `Not compatible with "${currentFeatureId}"`;
      else if (!isRunnable && b.disabledReason) disabledReason = b.disabledReason;
      else if (!isRunnable) disabledReason = "Not runnable";

      const item = document.createElement("div");
      item.className = "comfymodal-studio-compare-item";
      if (!canSelect) item.style.opacity = "0.45";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "comfymodal-studio-compare-checkbox";
      cb.setAttribute("data-backend-id", bId);
      cb.setAttribute("data-testid", `compare-preset-${bId}`);
      if (!canSelect) cb.disabled = true;
      cb.checked = canSelect && compareIds.includes(bId);
      cb.addEventListener("change", () => {
        const current = (state.playground && state.playground.compareBackendIds) || [];
        let updated;
        if (cb.checked) {
          updated = [...current, bId];
        } else {
          updated = current.filter((id) => id !== bId);
        }
        state.playground.compareBackendIds = updated;
        // Recalculate eligible axes and clear ineligible ones
        const eligible = recalcEligibleAxes(state, presets);
        state.playground._eligibleAxes = eligible;
        // Remove axes that are no longer eligible
        const axes = state.playground.experimentAxes || {};
        Object.keys(axes).forEach((ctrlId) => {
          if (!eligible.includes(ctrlId)) {
            delete axes[ctrlId];
          }
        });
        if (actions && actions.persistExperimentDraft) {
          actions.persistExperimentDraft();
        }
        const matrixBody = container.parentNode
          ? container.parentNode.querySelector('[data-testid="matrix-body"]')
          : null;
        if (matrixBody) {
          updateMatrixSummary(matrixBody, state);
        }
        // Trigger full Playground re-render so run-button, controls,
        // and axis checkboxes reflect the new compare selection.
        if (context && context.setPage) {
          context.setPage("playground");
        }
      });
      item.appendChild(cb);

      const label = document.createElement("span");
      label.textContent = b.label || b.id || "Unknown";
      label.style.fontSize = "var(--font-size-sm)";
      item.appendChild(label);

      if (disabledReason) {
        const reasonEl = document.createElement("span");
        reasonEl.textContent = ` (${disabledReason})`;
        reasonEl.style.fontSize = "var(--font-size-xs)";
        reasonEl.style.color = "var(--color-text-muted)";
        reasonEl.style.marginLeft = "4px";
        item.appendChild(reasonEl);
      }

      list.appendChild(item);
    });
  }).catch(() => {
    const errorMsg = document.createElement("p");
    errorMsg.className = "comfymodal-studio-empty-state";
    errorMsg.textContent = "Could not load presets.";
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
        if (!parent || !parent.isConnected) return;
        const existingEditors = parent.querySelectorAll(`[data-testid="axis-editor-${controlId}"]`);
        for (const existing of existingEditors) {
          if (existing.isConnected) existing.remove();
        }
        parent.insertBefore(editor, controlEl.nextSibling);
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
    // Disabled with explanation for select controls like LoRA
    const disabledMsg = document.createElement("p");
    disabledMsg.textContent = "Axis configuration not available for this control type. Configure in Legacy Setup.";
    disabledMsg.style.fontSize = "var(--font-size-xs)";
    disabledMsg.style.color = "var(--color-text-muted)";
    disabledMsg.style.fontStyle = "italic";
    valuesArea.appendChild(disabledMsg);
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
          input.className = "comfymodal-input comfymodal-studio-textarea";
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

      // Plus button — appends a new empty value
      const addBtn = document.createElement("button");
      addBtn.textContent = "+";
      addBtn.className = "comfymodal-secondary-btn";
      addBtn.style.fontSize = "12px";
      addBtn.style.padding = "2px 8px";
      addBtn.setAttribute("data-testid", "axis-add-value-" + controlId);
      addBtn.setAttribute("aria-label", "Add value");
      addBtn.addEventListener("click", function () {
        const currentVals = collectValues();
        currentVals.push("");
        if (actions && actions.updateExperimentAxisValues) {
          actions.updateExperimentAxisValues(controlId, currentVals);
        }
        _renderRepeatedValues();
      });
      valuesArea.appendChild(addBtn);

      // Quick-add buttons for common steps/guidance values (preserving existing behavior)
      if (def.type === "number") {
        let quickValues = [];
        if (controlId === "steps") quickValues = [10, 20, 30, 50];
        else if (controlId === "guidance") quickValues = [5, 7, 10, 15];

        if (quickValues.length > 0) {
          const quickRow = document.createElement("div");
          quickRow.style.marginTop = "4px";
          quickRow.style.display = "flex";
          quickRow.style.gap = "4px";
          quickValues.forEach(function (v) {
            const btn = document.createElement("button");
            btn.className = "comfymodal-secondary-btn";
            btn.textContent = String(v);
            btn.style.fontSize = "10px";
            btn.style.padding = "2px 6px";
            btn.addEventListener("click", function () {
              const currentVals = collectValues();
              if (!currentVals.includes(String(v))) {
                currentVals.push(String(v));
                if (actions && actions.updateExperimentAxisValues) {
                  actions.updateExperimentAxisValues(controlId, currentVals);
                }
                _renderRepeatedValues();
              }
            });
            quickRow.appendChild(btn);
          });
          valuesArea.appendChild(quickRow);
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
    } else {
      var errMsg = (result && result.message) || "Experiment run failed.";
      if (actions && actions.setRunState) {
        actions.setRunState({ status: "error", message: errMsg });
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

  if (canonicalPresetIds.length === 0) return "Select at least one preset to run an experiment.";
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

  // Only submit axes that are eligible (supported by all selected presets)
  const eligibleAxes = (state.playground && state.playground._eligibleAxes) || [];
  Object.entries(axes).forEach(([ctrlId, def]) => {
    if (def && def.enabled && def.values && def.values.length > 0 && eligibleAxes.includes(ctrlId)) {
      var parsedValues = def.values.map(function (v) {
        // Parse numeric strings so the backend schema validation
        // (which checks isinstance(value, int)) accepts them.
        if (typeof v === "string" && v.trim() !== "" && !isNaN(Number(v))) return Number(v);
        return v;
      });
      experimentDef.axes[ctrlId] = { enabled: true, values: parsedValues };
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

// ── Full experiment mode renderer ────────────────────────────────────────

export function renderExperimentMode(state, actions, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-experiment-mode";
  container.setAttribute("data-testid", "experiment-mode");

  // Compare Backends block (context passed explicitly)
  container.appendChild(renderCompareBackends(state, actions, context || {}));

  // Matrix Summary block
  container.appendChild(renderMatrixSummary(state, actions));

  // Run Experiment button — inside the experiment block so it's visible
  // alongside the experiment controls, not buried at the bottom of the
  // entire control panel.
  container.appendChild(renderExperimentRunButton(state, actions, context));

  // Experiment Settings button — scrolls controls container into view and
  // focuses the first eligible axis checkbox, without navigating away.
  var settingsBtn = document.createElement("button");
  settingsBtn.className = "comfymodal-secondary-btn";
  settingsBtn.textContent = "Experiment Settings";
  settingsBtn.setAttribute("data-testid", "experiment-settings-btn");
  settingsBtn.setAttribute("aria-label", "Scroll to experiment controls and focus first axis");
  settingsBtn.addEventListener("click", function () {
    var controlsContainer = document.querySelector('[data-testid="controls-container"]');
    if (controlsContainer) {
      controlsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
      var firstAxisCheckbox = controlsContainer.querySelector(
        '[data-testid^="axis-checkbox-"] input[type="checkbox"]:not([disabled])'
      );
      if (firstAxisCheckbox) {
        firstAxisCheckbox.focus({ preventScroll: true });
      }
    }
  });
  container.appendChild(settingsBtn);

  return container;
}
