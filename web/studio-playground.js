// Modal Studio — Playground
//
// Default Studio page with left control panel and right workspace.
// Image-edit interactions are honest disabled future-work placeholders.
// Uses the feature registry for all control rendering.
// Experiment mode is an overlay on controls, not a separate page.

import { FEATURE_SPECS, CONTROL_DEFS } from "./studio-feature-registry.js";
import {
  renderExperimentToggle,
  renderExperimentMode,
  enhanceControlWithAxisCheckbox,
} from "./studio-experiment-mode.js";
import { getRuntimePresets } from "./studio-backend.js";
import { runStudioPreset } from "./studio-backend-api.js";
import {
  canRunExperiment,
  getExperimentDisabledReason,
  executeExperimentRun,
} from "./studio-experiment-mode.js";

// ── Element helper ───────────────────────────────────────────────────────

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    } else if (k === "value") {
      e.value = props[k];
    } else if (k === "dataset") {
      Object.assign(e.dataset, props[k]);
    } else if (k === "disabled" || k === "checked" || k === "hidden" || k === "readonly" || k === "required") {
      if (props[k]) e.setAttribute(k, "");
      else e.removeAttribute(k);
    } else {
      e.setAttribute(k, props[k]);
    }
  }
  for (const c of (Array.isArray(children) ? children : [children])) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

// ── Main Playground renderer ─────────────────────────────────────────────

export function renderPlayground(state, context) {
  const container = el("div", { class: "comfymodal-studio-playground" });

  const leftPanel = renderControlPanel(state, context);
  const rightWorkspace = renderWorkspace(state, context);

  container.appendChild(leftPanel);
  container.appendChild(rightWorkspace);

  return container;
}

// ── Left Control Panel ───────────────────────────────────────────────────

function renderControlPanel(state, context) {
  const panel = el("div", { class: "comfymodal-studio-control-panel", "data-testid": "control-panel" });

  const isExperiment = state.playground && state.playground.experimentMode;
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const currentSpec = FEATURE_SPECS.find((f) => f.id === currentFeatureId) || FEATURE_SPECS[0];

  // Actions for state mutations (called by event handlers)
  const actions = buildActions(state, context);

  // Experiment toggle (always at top of control panel)
  panel.appendChild(renderExperimentToggle(state, actions));

  // If experiment mode, render experiment-mode controls (context passed explicitly)
  if (isExperiment) {
    const expBlock = renderExperimentMode(state, actions, context);
    panel.appendChild(expBlock);
  }

  // ── Backend Selector ───────────────────────────────────────────────
  panel.appendChild(renderControlGroup("Backend", renderBackendSelector(state, actions, context)));

  // ── Controls from feature registry ─────────────────────────────────
  const controlsContainer = el("div", { class: "comfymodal-studio-controls", "data-testid": "controls-container" });

  currentSpec.controls.forEach((ctrlId) => {
    const def = CONTROL_DEFS[ctrlId];
    if (!def) return;

    // Skip instruction for txt2img (only relevant for image-edit features)
    if (ctrlId === "instruction" && !currentSpec.isPlaceholder) return;

    // Only skip negative_prompt for placeholder features (prompt is still shown for image-edit)
    if (ctrlId === "negative_prompt" && currentSpec.isPlaceholder) return;

    const controlRow = renderControl(def, state, actions);

    // In experiment mode, add axis checkbox for eligible controls
    if (isExperiment && def.experimentEligible) {
      const checkboxWrapper = enhanceControlWithAxisCheckbox(controlRow, ctrlId, state, actions);
      if (checkboxWrapper && controlRow.firstChild) {
        controlRow.insertBefore(checkboxWrapper, controlRow.firstChild);
      }
    }

    controlsContainer.appendChild(controlRow);
  });

  // If current feature is a placeholder, show honest disabled state
  if (currentSpec.isPlaceholder) {
    const placeholderMsg = el("div", { class: "comfymodal-studio-placeholder-notice" }, [
      el("p", {
        text: currentSpec.placeholderReason || "This feature is not implemented yet.",
        style: "color:var(--color-text-muted);font-size:var(--font-size-sm);font-style:italic;",
      }),
    ]);
    controlsContainer.appendChild(placeholderMsg);
  }

  // Add mask controls section for image-edit/inpaint-like features (txt2img, object_remove, object_replace)
  if (currentFeatureId === "txt2img" || currentFeatureId === "object_remove" || currentFeatureId === "object_replace") {
    controlsContainer.appendChild(renderMaskControlsSection(state, actions));
  }

  panel.appendChild(controlsContainer);

  // ── Run Button ─────────────────────────────────────────────────────
  panel.appendChild(renderRunButton(state, context, actions, isExperiment));

  return panel;
}

// ── Actions builder ──────────────────────────────────────────────────────

function buildActions(state, context) {
  return {
    setFeature(featureId) {
      state.playground.featureId = featureId;
      if (context && context.setPage) {
        // Stay on playground, just re-render by triggering parent refresh
        context.setPage("playground");
      }
    },
    setBackend(backendId) {
      state.playground.selectedBackendId = backendId;
      // Re-render so Run button reflects selection
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    setControl(ctrlId, value) {
      if (!state.playground.controls) state.playground.controls = {};
      state.playground.controls[ctrlId] = value;
    },
    setExperimentMode(enabled) {
      state.playground.experimentMode = enabled;
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    toggleExperimentAxis(ctrlId, enabled) {
      if (!state.playground.experimentAxes) state.playground.experimentAxes = {};
      if (enabled) {
        state.playground.experimentAxes[ctrlId] = {
          enabled: true,
          values: [CONTROL_DEFS[ctrlId] ? CONTROL_DEFS[ctrlId].defaultValue : ""],
        };
      } else {
        delete state.playground.experimentAxes[ctrlId];
      }
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    updateExperimentAxisValues(ctrlId, values) {
      if (!state.playground.experimentAxes) state.playground.experimentAxes = {};
      if (!state.playground.experimentAxes[ctrlId]) {
        state.playground.experimentAxes[ctrlId] = { enabled: true, values: [] };
      }
      state.playground.experimentAxes[ctrlId].values = values;
      state.playground.experimentAxes[ctrlId].enabled = true;
    },
    navigateToLegacySetup() {
      if (context && context.setPage) {
        state.settings.activeLegacyTab = "setup";
        context.setPage("settings");
      }
    },
    navigateToBackendTab() {
      if (context && context.setPage) {
        context.setPage("backend");
      }
    },
    navigateToHistory() {
      if (context && context.setPage) {
        context.setPage("history");
      }
    },
    setRunState(runState) {
      if (!state.playground) state.playground = {};
      state.playground.runState = runState;
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
  };
}

// ── Control Group wrapper ────────────────────────────────────────────────

function renderControlGroup(labelText, inputEl) {
  const group = el("div", { class: "comfymodal-studio-control-group" });
  if (labelText) {
    const label = el("label", { class: "comfymodal-studio-control-label", text: labelText });
    group.appendChild(label);
  }
  if (inputEl) group.appendChild(inputEl);
  return group;
}

// ── Backend Selector ─────────────────────────────────────────────────────
//
// Loads backends from the Studio backend abstraction (getBackends).
// Filters by feature compatibility when appropriate.
// In empty state, links to the Backend tab instead of Legacy Setup.

function renderBackendSelector(state, actions, context) {
  const container = el("div", { class: "comfymodal-studio-backend-selector", "data-testid": "backend-selector" });

  const select = el("select", {
    class: "comfymodal-input comfymodal-studio-select",
    "data-testid": "backend-select",
  });
  const loadingOpt = el("option", { value: "", text: "Loading backends…", disabled: true, selected: true });
  select.appendChild(loadingOpt);
  select.disabled = true;
  container.appendChild(select);

    // Async load presets through the Studio abstraction (runtime selectors only)
  const apiBase = (context && context.apiBase) || "/comfymodal";
  getRuntimePresets({ apiBase }).then((backends) => {
    while (select.firstChild) select.removeChild(select.firstChild);

    if (!backends || backends.length === 0) {
      // Empty state: show disabled select + link to Backend tab
      const emptyOpt = el("option", { value: "", text: "No backends available", disabled: true, selected: true });
      select.appendChild(emptyOpt);
      select.disabled = true;

      // Remove any existing empty message and add fresh one linking to Backend tab
      const existingMsg = container.querySelector(".comfymodal-studio-backend-empty-msg");
      if (existingMsg) existingMsg.remove();

      const emptyMsg = el("p", {
        class: "comfymodal-studio-empty-state comfymodal-studio-backend-empty-msg",
        style: "font-size:var(--font-size-xs);color:var(--color-text-muted);margin-top:4px;",
      });
      emptyMsg.textContent = "No backends configured. ";
      const link = el("a", {
        text: "Go to Backend tab",
        style: "color:var(--color-accent);cursor:pointer;",
        onclick: (e) => {
          e.preventDefault();
          if (actions && actions.navigateToBackendTab) actions.navigateToBackendTab();
        },
      });
      emptyMsg.appendChild(link);
      emptyMsg.appendChild(document.createTextNode(" to add backends."));
      container.appendChild(emptyMsg);
      return;
    }

    // Populate select with loaded backends
    select.disabled = false;
    const placeholderOpt = el("option", { value: "", text: "Select a backend…", disabled: true, selected: true });
    select.appendChild(placeholderOpt);

    const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
    backends.forEach((b) => {
      const compat = b.compatibleFeatures || [];
      // Show all backends; compatibility is advisory
      const opt = el("option", { value: b.id || b.label || "", text: b.label || b.id || "Unknown" });
      if (compat.length > 0 && !compat.includes(currentFeatureId)) {
        opt.style.opacity = "0.5";
        opt.title = `Not tested with ${currentFeatureId}`;
      }
      select.appendChild(opt);
    });

    // Set current selection from state
    const currentId = state.playground && state.playground.selectedBackendId;
    if (currentId) {
      select.value = currentId;
    }

    // Wire change handler to update state
    select.addEventListener("change", () => {
      if (actions && actions.setBackend) {
        actions.setBackend(select.value);
      }
    });
  }).catch(() => {
    while (select.firstChild) select.removeChild(select.firstChild);
    const errOpt = el("option", { value: "", text: "Could not load backends", disabled: true, selected: true });
    select.appendChild(errOpt);
    select.disabled = true;
  });

  return container;
}

// ── Info Hint helper ─────────────────────────────────────────────────────
//
// Creates a compact info icon with a hover/focus tooltip to replace bulky
// visible description paragraphs under headings and section labels.

export function createInfoHint(text, options) {
  const hint = el("span", {
    class: "comfymodal-studio-info-hint",
    "data-testid": "info-hint",
    tabindex: "0",
    role: "tooltip",
    "aria-label": text,
  });
  hint.textContent = "\u24d8";  // ⓘ circled info icon

  const tooltip = el("span", {
    class: "comfymodal-studio-tooltip",
    text: text,
  });
  if (options && options.maxWidth) {
    tooltip.style.maxWidth = options.maxWidth;
  }
  hint.appendChild(tooltip);

  hint.addEventListener("mouseenter", () => { tooltip.style.display = "block"; });
  hint.addEventListener("mouseleave", () => { tooltip.style.display = ""; });
  hint.addEventListener("focus", () => { tooltip.style.display = "block"; });
  hint.addEventListener("blur", () => { tooltip.style.display = ""; });

  return hint;
}

// ── Render a single control ──────────────────────────────────────────────

function renderControl(def, state, actions) {
  const value = ((state.playground && state.playground.controls) || {})[def.id] ?? def.defaultValue;
  const group = el("div", {
    class: "comfymodal-studio-control-group",
    "data-control-id": def.id,
    "data-testid": `control-${def.id}`,
  });

  const label = el("label", {
    class: "comfymodal-studio-control-label",
    text: def.label,
  });
  group.appendChild(label);

  if (def.helpText) {
    group.appendChild(createInfoHint(def.helpText));
  }

  let input;
  if (def.type === "textarea") {
    input = el("textarea", {
      class: "comfymodal-input comfymodal-studio-textarea",
      placeholder: def.placeholder || "",
      value: String(value),
      "data-testid": `input-${def.id}`,
    });
    input.addEventListener("input", () => {
      if (actions.setControl) actions.setControl(def.id, input.value);
    });
  } else if (def.type === "select") {
    input = el("select", {
      class: "comfymodal-input comfymodal-studio-select",
      "data-testid": `input-${def.id}`,
    });
    const emptyOpt = el("option", { value: "", text: "Default" });
    input.appendChild(emptyOpt);
    input.disabled = true;
    // Disabled: LoRA selection is done in Legacy Setup
    const note = el("span", {
      class: "comfymodal-studio-control-note",
      text: "Configure in Legacy Setup",
      style: "font-size:var(--font-size-xs);color:var(--color-text-muted);",
    });
    group.appendChild(note);
  } else {
    // number type
    input = el("input", {
      type: "number",
      class: "comfymodal-input comfymodal-studio-number-input",
      value: String(value),
      min: def.min != null ? String(def.min) : "",
      max: def.max != null ? String(def.max) : "",
      step: def.step != null ? String(def.step) : "any",
      "data-testid": `input-${def.id}`,
    });
    input.addEventListener("input", () => {
      if (actions.setControl) actions.setControl(def.id, parseFloat(input.value) || input.value);
    });
  }

  if (input) group.appendChild(input);
  return group;
}

// ── Mask Controls Section ────────────────────────────────────────────────

function renderMaskControlsSection(state, actions) {
  const section = el("div", { class: "comfymodal-studio-mask-controls", "data-testid": "mask-controls" });

  const heading = el("h4", {
    class: "comfymodal-studio-section-heading",
    text: "Mask",
    style: "font-size:var(--font-size-sm);margin:var(--space-md) 0 var(--space-xs);color:var(--color-text-secondary);",
  });
  section.appendChild(heading);

  const maskBlurDef = CONTROL_DEFS.mask_blur;
  const maskExpandDef = CONTROL_DEFS.mask_expand;

  if (maskBlurDef) section.appendChild(renderControl(maskBlurDef, state, actions));
  if (maskExpandDef) section.appendChild(renderControl(maskExpandDef, state, actions));

  return section;
}

// ── Run Button ───────────────────────────────────────────────────────────

function renderRunButton(state, context, actions, isExperiment) {
  const container = el("div", { class: "comfymodal-studio-run-section" });

  const btnText = isExperiment ? "Run Experiment" : "Run";
  const testId = isExperiment ? "run-experiment-btn" : "run-btn";
  const btn = el("button", {
    class: "comfymodal-primary-btn",
    disabled: true,
    text: btnText,
    "data-testid": testId,
    title: "",
  });

  const reason = el("div", { class: "comfymodal-studio-disabled-reason" });
  container.appendChild(btn);
  container.appendChild(reason);

  const apiBase = (context && context.apiBase) || "/comfymodal";
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const runState = state.playground && state.playground.runState;

  if (runState && (runState.status === "running" || runState.status === "submitted")) {
    const isRunning = runState.status === "running";
    btn.disabled = true;
    btn.textContent = isRunning ? "Running\u2026" : "Submitted";
    btn.title = isRunning ? "Run in progress" : "Run submitted successfully";
    if (isRunning) {
      reason.appendChild(el("p", {
        text: "Your run has been submitted\u2026",
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      }));
    } else {
      const viewLink = el("a", {
        text: "View in History",
        style: "font-size:var(--font-size-sm);color:var(--color-accent);cursor:pointer;",
        onclick: (e) => {
          e.preventDefault();
          if (actions && actions.navigateToHistory) actions.navigateToHistory();
        },
      });
      reason.appendChild(viewLink);
    }
    return container;
  }

  if (runState && runState.status === "error") {
    btn.disabled = true;
    btn.textContent = "Run Failed";
    btn.title = "Run failed";
    reason.appendChild(el("p", {
      text: runState.message || "Run failed. Try again.",
      style: "font-size:var(--font-size-sm);color:var(--color-danger);margin:4px 0 0;",
    }));
    const retryBtn = el("button", {
      class: "comfymodal-secondary-btn",
      text: "Dismiss",
      style: "font-size:10px;padding:2px 8px;margin-top:4px;",
      onclick: () => {
        if (actions && actions.setRunState) actions.setRunState(null);
      },
    });
    reason.appendChild(retryBtn);
    return container;
  }

  // Async-load presets to determine runnability
  getRuntimePresets({ apiBase }).then((presets) => {
    while (reason.firstChild) reason.removeChild(reason.firstChild);

    if (!presets || presets.length === 0) {
      btn.disabled = true;
      btn.title = "No backend presets configured";

      const p1 = el("p", {
        text: "No backend presets configured. ",
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      });
      const link = el("a", {
        text: "Go to Backend tab",
        style: "font-size:var(--font-size-sm);color:var(--color-accent);cursor:pointer;",
        onclick: (e) => {
          e.preventDefault();
          actions.navigateToBackendTab();
        },
      });
      reason.appendChild(p1);
      reason.appendChild(link);
      reason.appendChild(document.createTextNode(" to create presets."));
      return;
    }

    if (isExperiment) {
      // ── Experiment mode run button ──────────────────────────────────
      const canRun = canRunExperiment(state);
      const expReason = getExperimentDisabledReason(state);

      if (!canRun || expReason) {
        btn.disabled = true;
        btn.title = expReason || "Cannot run experiment";
        reason.appendChild(el("p", {
          text: expReason || "Select presets to compare.",
          style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
        }));
      } else {
        btn.disabled = false;
        btn.title = "";
        btn.onclick = async () => {
          btn.disabled = true;
          btn.textContent = "Running\u2026";
          if (actions && actions.setRunState) actions.setRunState({ status: "running" });

          const result = await executeExperimentRun(state, context);

          if (result && result.status === "ok") {
            if (actions && actions.setRunState) {
              actions.setRunState({
                status: "submitted",
                experimentId: result.experimentId,
                message: result.message,
              });
            }
          } else {
            const errMsg = (result && result.message) || "Experiment run failed.";
            if (actions && actions.setRunState) {
              actions.setRunState({ status: "error", message: errMsg });
            }
          }
        };
      }
      return;
    }

    // ── Single run mode ──────────────────────────────────────────────
    const selectedId = state.playground && state.playground.selectedBackendId;
    if (!selectedId) {
      btn.disabled = true;
      btn.title = "Select a backend preset";
      reason.appendChild(el("p", {
        text: "Select or create a Backend Preset.",
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      }));
      return;
    }

    const preset = presets.find((p) => (p.id || p.label || "") === selectedId);
    if (!preset) {
      btn.disabled = true;
      btn.title = "Selected preset not found";
      reason.appendChild(el("p", {
        text: "Selected preset is no longer available.",
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      }));
      return;
    }

    const presetRunnable = preset.status === "runnable";
    const featureCompat = (preset.compatibleFeatures || []).includes(currentFeatureId);
    let disabledReason = "";

    if (preset.archived) {
      disabledReason = "This preset is archived.";
    } else if (!featureCompat) {
      disabledReason = `This preset does not support "${currentFeatureId}".`;
    } else if (!presetRunnable && preset.disabledReason) {
      disabledReason = preset.disabledReason;
    } else if (!presetRunnable) {
      disabledReason = "This preset is not runnable.";
    }

    if (disabledReason) {
      btn.disabled = true;
      btn.title = disabledReason;
      reason.appendChild(el("p", {
        text: disabledReason,
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      }));
    } else {
      btn.disabled = false;
      btn.title = "";
      btn.onclick = async () => {
        btn.disabled = true;
        btn.textContent = "Running\u2026";
        if (actions && actions.setRunState) actions.setRunState({ status: "running" });

        const controls = (state.playground && state.playground.controls) || {};
        const result = await runStudioPreset(apiBase, {
          presetId: preset.id || selectedId,
          featureId: currentFeatureId,
          controls: controls,
          metadata: { source: "studio_playground" },
        });

        if (result && result.status === "ok") {
          if (actions && actions.setRunState) {
            actions.setRunState({
              status: "submitted",
              runId: result.runId || result.experimentId,
              experimentId: result.experimentId,
            });
          }
        } else {
          const errMsg = (result && result.message) || "Run failed.";
          if (actions && actions.setRunState) {
            actions.setRunState({ status: "error", message: errMsg });
          }
        }
      };
    }
  }).catch(() => {
    while (reason.firstChild) reason.removeChild(reason.firstChild);
    reason.appendChild(el("p", {
      text: "Could not load presets.",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    }));
  });

  return container;
}

// ── Right Workspace ──────────────────────────────────────────────────────

function renderWorkspace(state, context) {
  const workspace = el("div", { class: "comfymodal-studio-workspace", "data-testid": "workspace" });

  // Feature tabs
  workspace.appendChild(renderFeatureTabs(state, context));

  // Canvas area
  workspace.appendChild(renderCanvas(state, context));

  // Recent runs filmstrip
  workspace.appendChild(renderFilmstrip(state, context));

  return workspace;
}

// ── Feature Tabs ─────────────────────────────────────────────────────────

function renderFeatureTabs(state, context) {
  const tabs = el("div", { class: "comfymodal-studio-feature-tabs", "data-testid": "feature-tabs" });

  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";

  FEATURE_SPECS.forEach((spec) => {
    const isActive = spec.id === currentFeatureId;
    const tab = el("button", {
      class: `comfymodal-studio-feature-tab${isActive ? " active" : ""}`,
      "data-feature": spec.id,
      "data-testid": `feature-tab-${spec.id}`,
      text: spec.label,
      onclick: () => {
        if (state.playground) state.playground.featureId = spec.id;
        if (context && context.setPage) context.setPage("playground");
      },
    });
    tabs.appendChild(tab);
  });

  return tabs;
}

// ── Canvas ───────────────────────────────────────────────────────────────

function renderCanvas(state, context) {
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const currentSpec = FEATURE_SPECS.find((f) => f.id === currentFeatureId);

  const canvas = el("div", {
    class: "comfymodal-studio-canvas",
    "data-testid": "canvas-area",
  });

  if (currentSpec && currentSpec.isPlaceholder) {
    // Honest disabled placeholder for image-edit features
    const placeholderMsg = el("div", { class: "comfymodal-studio-placeholder-notice", style: "text-align:center;padding:40px 20px;" }, [
      el("p", { text: `${currentSpec.label} — Not Implemented`, style: "font-weight:var(--font-weight-semibold);margin-bottom:8px;" }),
      el("p", { text: currentSpec.placeholderReason || "This feature is not available in this release.", style: "font-size:var(--font-size-sm);color:var(--color-text-muted);" }),
    ]);
    canvas.appendChild(placeholderMsg);
  } else {
    canvas.appendChild(el("p", {
      text: "Generated output will appear here.",
      style: "color:var(--color-text-muted);",
    }));
  }

  return canvas;
}

// ── Filmstrip ────────────────────────────────────────────────────────────

function renderFilmstrip(state, context) {
  const filmstrip = el("div", {
    class: "comfymodal-studio-filmstrip",
    "data-testid": "filmstrip",
  });

  const msg = el("p", {
    class: "comfymodal-studio-empty-state",
    text: "Recent runs will appear here once you create experiments. Use Settings > Legacy Setup to run experiments.",
    style: "font-size:var(--font-size-xs);color:var(--color-text-muted);padding:8px;",
  });
  filmstrip.appendChild(msg);

  return filmstrip;
}
