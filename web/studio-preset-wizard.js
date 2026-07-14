// Modal Studio — Preset Wizard
//
// Side-panel wizard for creating or editing a Studio preset from the
// current ComfyUI graph.
// Steps: Feature Type → Required Bindings → Exposed Controls → Details
// Wires into studio-backend.js as the primary "Make Preset" flow.
// Supports edit mode: pass existingPreset + existingSnapshot to pre-fill.

import { el } from "./studio-ui.js";
import {
  isGraphAvailable,
  getComfyGraphContext,
  beginGraphBindingCapture,
  cancelGraphBinding,
  getSelectedGraphNodeTarget,
} from "./studio-graph-binding.js";
import { captureCurrentComfyGraph } from "./studio-backend-capture.js";
import { createSnapshot, createPreset, updateSnapshot, updatePreset } from "./studio-backend-api.js";
import {
  CONTROL_BINDING_DEFS,
  getRequiredBindingsForFeature,
  getOptionalBindingsForFeature,
} from "./studio-preset-capabilities.js";

// ── Feature definitions for wizard steps ────────────────────────────────
// Aligned with studio-preset-capabilities.js definitions.

const FEATURE_DEFS = {
  txt2img: {
    id: "txt2img",
    label: "Txt2Img",
    description: "Standard text-to-image generation",
    requiredBindings: getRequiredBindingsForFeature("txt2img"),
    optionalBindings: getOptionalBindingsForFeature("txt2img"),
  },
  object_remove: {
    id: "object_remove",
    label: "Object Remove",
    description: "Remove an object from an image",
    requiredBindings: getRequiredBindingsForFeature("object_remove"),
    optionalBindings: getOptionalBindingsForFeature("object_remove"),
  },
  object_replace: {
    id: "object_replace",
    label: "Object Replace",
    description: "Replace an object in an image",
    requiredBindings: getRequiredBindingsForFeature("object_replace"),
    optionalBindings: getOptionalBindingsForFeature("object_replace"),
  },
};

// ── Wizard state ────────────────────────────────────────────────────────

let _wizardState = null;
let _wizardRoot = null;

function makeInitialState(existingPreset, existingSnapshot) {
  const state = {
    step: "features",           // features | bindings | details | saving | saved | error
    selectedFeatures: [],
    bindings: {},               // { [bindingKey]: bindingTarget | null }
    bindingCaptureActive: null, // bindingKey currently being captured, or null
    details: {
      name: "",
      description: "",
    },
    graphCaptured: false,
    graphJson: null,
    apiPromptJson: null,
    captureWarnings: [],
    // Server responses
    snapshotResult: null,
    presetResult: null,
    errorMessage: "",
    // Edit-mode fields
    isEdit: false,
    existingPreset: null,
    existingSnapshot: null,
    existingPresetId: null,
    existingSnapshotId: null,
  };

  // ── Edit mode: pre-fill from existing preset + snapshot ─────────────
  if (existingPreset) {
    state.isEdit = true;
    state.existingPreset = existingPreset;
    state.existingPresetId = existingPreset.id;
    state.step = "bindings"; // skip feature selection in edit mode
    state.selectedFeatures = existingPreset.compatibleFeatures || [];
    state.details.name = existingPreset.label || existingPreset.name || "";
    state.details.description = existingPreset.description || "";

    if (existingSnapshot) {
      state.existingSnapshot = existingSnapshot;
      state.existingSnapshotId = existingSnapshot.id;
      state.graphJson = existingSnapshot.graphJson || null;
      state.apiPromptJson = existingSnapshot.apiPromptJson || null;
      state.graphCaptured = true;
    }

    // Pre-fill bindings from either preset's or snapshot's nodeBindings
    const srcBindings = existingPreset.nodeBindings || (existingSnapshot && existingSnapshot.nodeBindings) || {};
    Object.entries(srcBindings).forEach(([key, val]) => {
      if (val && val.nodeId) {
        state.bindings[key] = { ...val };
      }
    });

    // Pre-fill capture warnings
    state.captureWarnings = (existingSnapshot && existingSnapshot.warnings) || [];
  }

  return state;
}

// ── Public API ───────────────────────────────────────────────────────────

export function openPresetWizard(onDone, apiBase, existingPreset, existingSnapshot) {
  closePresetWizard(); // Clean up any existing wizard first

  _wizardState = makeInitialState(existingPreset, existingSnapshot);
  _wizardState._onDone = onDone;
  _wizardState._apiBase = apiBase || "/comfymodal";

  // Create wizard root element
  _wizardRoot = el("div", { class: "comfymodal-studio-wizard-overlay" });

  // Add wizard-mode class to modal root for side-panel layout
  document.body.classList.add("comfymodal-studio-wizard-mode");

  const modalRoot = document.querySelector(".comfymodal-studio-modal");
  const overlayRoot = document.querySelector(".comfymodal-testing-overlay");
  if (modalRoot) {
    modalRoot.classList.add("comfymodal-studio-wizard-mode");
  }
  if (overlayRoot) {
    overlayRoot.classList.add("comfymodal-studio-wizard-mode");
  }

  const panel = el("div", { class: "comfymodal-studio-wizard-panel" });
  _wizardRoot.appendChild(panel);

  // Insert wizard next to the page container in the modal
  const pageContainer = document.querySelector(".comfymodal-studio-pagecontainer");
  if (pageContainer && pageContainer.parentNode) {
    pageContainer.parentNode.insertBefore(_wizardRoot, pageContainer.nextSibling);
  } else {
    // Fallback: append to body
    document.body.appendChild(_wizardRoot);
  }

  renderWizard(panel, _wizardState);

  // Notify modal layer that wizard is opening so it can release
  // background inertness (blocked by _inertBackground(true) in
  // open_testing_modal). The wizard's graph binding capture
  // (beginGraphBindingCapture) needs the underlying ComfyUI graph
  // clickable — inert on ancestors blocks all pointer events.
  document.dispatchEvent(new CustomEvent("comfymodal:wizard-opening"));
}

export function closePresetWizard() {
  // Clean up graph binding capture if active
  cancelGraphBinding();

  // Remove any binding capture hint elements
  const hints = document.querySelectorAll(".comfymodal-binding-capture-hint");
  hints.forEach((h) => h.parentNode && h.parentNode.removeChild(h));

  // Remove wizard-mode class
  document.body.classList.remove("comfymodal-studio-wizard-mode");
  const modalRoot = document.querySelector(".comfymodal-studio-modal");
  const overlayRoot = document.querySelector(".comfymodal-testing-overlay");
  if (modalRoot) {
    modalRoot.classList.remove("comfymodal-studio-wizard-mode");
  }
  if (overlayRoot) {
    overlayRoot.classList.remove("comfymodal-studio-wizard-mode");
  }

  if (_wizardRoot && _wizardRoot.parentNode) {
    _wizardRoot.parentNode.removeChild(_wizardRoot);
  }

  _wizardRoot = null;
  _wizardState = null;

  // Notify modal layer that wizard has closed so it can restore
  // background inertness (if the parent modal is still open).
  document.dispatchEvent(new CustomEvent("comfymodal:wizard-closed"));
}

// ── Render helpers ──────────────────────────────────────────────────────

function renderWizard(panel, state) {
  const scrollTop = panel.scrollTop;
  while (panel.firstChild) panel.removeChild(panel.firstChild);

  // Header
  const headerTitle = state.isEdit ? "Edit Preset" : "Make Preset";
  const header = el("div", { class: "comfymodal-studio-wizard-header" }, [
    el("h3", { text: headerTitle, class: "comfymodal-studio-wizard-title" }),
    el("button", {
      class: "comfymodal-studio-wizard-close",
      text: "\u00d7",
      onclick: () => closePresetWizardAndNotify(),
    }),
  ]);
  panel.appendChild(header);

  // Step indicator (skip in edit mode — edit starts at bindings)
  if (!state.isEdit) {
    const stepNames = ["Feature Type", "Bindings & Controls", "Details"];
    const stepKeys = ["features", "bindings", "details"];
    const currentStepIdx = stepKeys.indexOf(state.step);

    const stepIndicator = el("div", { class: "comfymodal-studio-wizard-steps" });
    stepKeys.forEach((key, idx) => {
      const isActive = key === state.step;
      const isDone = stepKeys.indexOf(state.step) > idx || (state.step === "saved" || state.step === "error");
      const dot = el("span", {
        class: "comfymodal-studio-wizard-step-dot"
          + (isActive ? " active" : "")
          + (isDone ? " done" : ""),
        text: isDone ? "\u2713" : String(idx + 1),
      });
      const label = el("span", {
        class: "comfymodal-studio-wizard-step-label"
          + (isActive ? " active" : ""),
        text: stepNames[idx],
      });
      stepIndicator.appendChild(dot);
      stepIndicator.appendChild(label);
      if (idx < stepKeys.length - 1) {
        stepIndicator.appendChild(el("span", {
          class: "comfymodal-studio-wizard-step-line"
            + (isDone ? " done" : ""),
        }));
      }
    });
    panel.appendChild(stepIndicator);
  }

  // Body
  const body = el("div", { class: "comfymodal-studio-wizard-body" });
  panel.appendChild(body);

  // Graph availability banner
  const graphContext = getComfyGraphContext();
  if (!graphContext.ok && !state.graphCaptured) {
    const banner = el("div", { class: "comfymodal-studio-wizard-graph-unavailable" }, [
      el("p", { text: graphContext.reason || "ComfyUI graph is not ready.", style: "color:#f87171;font-size:11px;margin:0;" }),
    ]);
    body.appendChild(banner);
  }

  // Render current step
  switch (state.step) {
    case "features":
      renderFeaturesStep(body, state);
      break;
    case "bindings":
      renderBindingsStep(body, state);
      break;
    case "details":
      renderDetailsStep(body, state);
      break;
    case "saving":
      renderSavingStep(body, state);
      break;
    case "saved":
      renderSavedStep(body, state);
      break;
    case "error":
      renderErrorStep(body, state);
      break;
  }

  // Helper: cancel any active binding capture before navigating steps
  function navigateStep(nextStep) {
    cancelGraphBinding();
    state.bindingCaptureActive = null;
    state.step = nextStep;
    renderWizard(panel, state);
  }

  // Footer
  const footer = el("div", { class: "comfymodal-studio-wizard-footer" });
  if (state.step === "features") {
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      text: "Continue to Bindings",
      disabled: state.selectedFeatures.length !== 1,
      onclick: () => {
        if (state.selectedFeatures.length !== 1) return;
        navigateStep("bindings");
      },
    }));
  } else if (state.step === "bindings") {
    const allRequiredBound = checkAllRequiredBindings(state);
    const graphOk = graphContext.ok || state.graphCaptured;

    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: state.isEdit ? "Cancel" : "Back to Features",
      onclick: () => {
        if (state.isEdit) {
          closePresetWizardAndNotify();
        } else {
          navigateStep("features");
        }
      },
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      text: "Continue to Details",
      disabled: !(allRequiredBound && graphOk),
      onclick: () => {
        if (!(allRequiredBound && graphOk)) return;
        navigateStep("details");
      },
    }));
  } else if (state.step === "details") {
    const canSave = state.details.name.trim().length > 0 && checkAllRequiredBindings(state) && (getComfyGraphContext().ok || state.graphCaptured);
    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: "Back to Bindings",
      onclick: () => navigateStep("bindings"),
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      "data-role": "save-preset",
      text: state.isEdit ? "Update Preset" : "Save Preset",
      disabled: !canSave,
      onclick: async () => {
        if (!(state.details.name.trim().length > 0 && checkAllRequiredBindings(state) && (getComfyGraphContext().ok || state.graphCaptured))) return;
        await executeSave(state);
        renderWizard(panel, state);
      },
    }));
  } else if (state.step === "saved") {
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      text: "Back to Backend",
      onclick: () => {
        closePresetWizardAndNotify();
      },
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: state.isEdit ? "Edit Again" : "Make Another",
      onclick: () => {
        closePresetWizard();
        if (state.isEdit) {
          openPresetWizard(state._onDone, state._apiBase, state.existingPreset, state.existingSnapshot);
        } else {
          openPresetWizard(state._onDone, state._apiBase);
        }
      },
    }));
  } else if (state.step === "error") {
    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: "Back to Details",
      onclick: () => navigateStep("details"),
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-destructive-btn",
      text: "Cancel",
      onclick: () => closePresetWizardAndNotify(),
    }));
  }
  panel.appendChild(footer);
  panel.scrollTop = scrollTop;
}

// ── Step: Features ──────────────────────────────────────────────────────

function renderFeaturesStep(body, state) {
  const heading = el("h4", { class: "comfymodal-studio-wizard-section-title", text: "Select Features" });
  body.appendChild(heading);

  const desc = el("p", {
    class: "comfymodal-studio-wizard-description",
    text: "Choose which features this preset should support.",
  });
  body.appendChild(desc);

  const featureList = el("div", { class: "comfymodal-studio-wizard-feature-list" });

  Object.values(FEATURE_DEFS).forEach((def) => {
    const isSelected = state.selectedFeatures.includes(def.id);
    const card = el("div", {
      class: "comfymodal-studio-wizard-feature-card"
        + (isSelected ? " selected" : ""),
      onclick: () => {
        cancelGraphBinding();
        state.bindingCaptureActive = null;
        state.selectedFeatures = isSelected ? [] : [def.id];
        renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
      },
    }, [
      el("div", { class: "comfymodal-studio-wizard-feature-check" }, [
        el("span", {
          class: "comfymodal-studio-wizard-checkbox" + (isSelected ? " checked" : ""),
          text: isSelected ? "\u2713" : "",
        }),
      ]),
      el("div", { class: "comfymodal-studio-wizard-feature-info" }, [
        el("strong", { text: def.label }),
        el("p", { text: def.description, style: "font-size:11px;color:#888;margin:2px 0 0;" }),
        el("p", {
          text: `Required: ${def.requiredBindings.map((b) => b.label).join(", ")}`,
          style: "font-size:10px;color:#666;margin:2px 0 0;",
        }),
      ]),
    ]);
    featureList.appendChild(card);
  });

  body.appendChild(featureList);
}

// ── Step: Bindings ──────────────────────────────────────────────────────

function renderBindingsStep(body, state) {
  const heading = el("h4", { class: "comfymodal-studio-wizard-section-title", text: "Node Bindings" });
  body.appendChild(heading);

  const desc = el("p", {
    class: "comfymodal-studio-wizard-description",
    text: "Click each binding row to enter capture mode, then click the corresponding node in the ComfyUI graph.",
  });
  body.appendChild(desc);

  const graphContext = getComfyGraphContext();
  const graphOk = graphContext.ok || state.graphCaptured;

  // ── API Graph row (read-only, captured automatically on save) ──────
  const apiRow = el("div", { class: "comfymodal-studio-wizard-binding-row" + (graphOk ? " bound" : "") }, [
    el("div", { class: "comfymodal-studio-wizard-binding-info" }, [
      el("strong", { style: "font-size:12px;", text: "API Graph" }),
      el("p", { style: "font-size:10px;color:#888;margin:2px 0 0;",
        text: graphOk
          ? "Captured automatically from the current ComfyUI graph when you save."
          : (graphContext.reason || "Graph unavailable"),
      }),
    ]),
    el("div", { class: "comfymodal-studio-wizard-binding-status" }, [
      el("span", {
        text: graphOk ? "Auto-captured on save" : "Unavailable",
        style: `font-size:10px;color:${graphOk ? "#4ade80" : "#f87171"};`,
      }),
    ]),
  ]);
  body.appendChild(apiRow);

  // ── Required bindings ─────────────────────────────────────────────
  const featureId = state.selectedFeatures[0];
  const requiredDefs = featureId ? getRequiredBindingsForFeature(featureId) : [];
  const optionalDefs = featureId ? getOptionalBindingsForFeature(featureId) : [];

  const reqHeading = el("h4", {
    style: "font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;margin:12px 0 4px;",
    text: "Required Bindings",
  });
  body.appendChild(reqHeading);

  const requiredList = renderBindingRowList(requiredDefs, state, graphContext);
  body.appendChild(requiredList);

  // ── Optional / Exposed Controls ──────────────────────────────────
  if (optionalDefs.length > 0) {
    const optHeading = el("h4", {
      style: "font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;margin:16px 0 4px;",
      text: "Exposed Controls (Optional)",
    });
    body.appendChild(optHeading);

    const optDesc = el("p", {
      style: "font-size:10px;color:#666;margin:0 0 4px;font-style:italic;",
      text: "Bind optional controls to expose them in the Playground.",
    });
    body.appendChild(optDesc);

    const optionalList = renderBindingRowList(optionalDefs, state, graphContext);
    body.appendChild(optionalList);
  }

  // ── Binding summary ──────────────────────────────────────────────
  const requiredKeys = collectRequiredBindings(state.selectedFeatures).map((b) => b.key);
  const boundCount = requiredKeys.filter((k) => state.bindings[k] && state.bindings[k].nodeId).length;
  const summary = el("p", {
    style: "font-size:11px;color:#888;margin-top:8px;",
    text: `${boundCount} of ${requiredKeys.length} required bindings complete • API graph ${graphOk ? "ready" : "unavailable"}`,
  });
  body.appendChild(summary);
}

// ── Binding row list renderer ────────────────────────────────────────────

function renderBindingRowList(bindingDefs, state, graphContext) {
  const list = el("div", { class: "comfymodal-studio-wizard-binding-list" });
  const graphOk = (graphContext && graphContext.ok) || state.graphCaptured;

  bindingDefs.forEach((bindingDef) => {
    const bindingValue = state.bindings[bindingDef.key];
    const isBound = Boolean(bindingValue && bindingValue.nodeId);
    const isCaptureActive = state.bindingCaptureActive === bindingDef.key;

    // Get label from CONTROL_BINDING_DEFS for consistency
    const defLabel = bindingDef.label || (CONTROL_BINDING_DEFS[bindingDef.key] && CONTROL_BINDING_DEFS[bindingDef.key].label) || bindingDef.key;
    const defHelp = bindingDef.helpText || (CONTROL_BINDING_DEFS[bindingDef.key] && CONTROL_BINDING_DEFS[bindingDef.key].helpText) || "";

    const row = el("div", {
      class: "comfymodal-studio-wizard-binding-row"
        + (isBound ? " bound" : "")
        + (isCaptureActive ? " capturing" : ""),
    }, [
      el("div", { class: "comfymodal-studio-wizard-binding-info" }, [
        el("strong", { style: "font-size:12px;", text: defLabel }),
        el("p", { style: "font-size:10px;color:#888;margin:2px 0 0;", text: defHelp }),
      ]),
      el("div", { class: "comfymodal-studio-wizard-binding-status" }, [
        isBound ? renderBoundValue(bindingValue, bindingDef) : (
          isCaptureActive
            ? el("span", { text: "Click a node...", style: "color:#fbbf24;font-size:10px;" })
            : el("span", { text: "Not bound", style: "color:#666;font-size:10px;" })
        ),
      ]),
    ]);

    // Click handler
    if (isCaptureActive) {
      // Capturing — clicking cancels
      row.addEventListener("click", (event) => {
        if (isWizardInteractiveTarget(event)) return;
        cancelGraphBinding();
        state.bindingCaptureActive = null;
        renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
      });
      row.classList.add("capturing-active");
      row.title = "Cancel capture";
      row.appendChild(el("button", {
        class: "comfymodal-secondary-btn",
        text: "Use Selected Node",
        style: "width:auto;padding:4px 8px;font-size:10px;align-self:flex-start;",
        onclick: (event) => {
          event.preventDefault();
          event.stopPropagation();
          const selected = getSelectedGraphNodeTarget();
          if (!selected) return;
          // Phase 4: extract widgetSchema from the selected candidate
          const selCandidate = _findSelectedCandidate(
            selected.candidates,
            { widgetName: selected.widgetName, inputName: selected.inputName, outputIndex: selected.outputIndex }
          );
          const selWidgetSchema = _buildWidgetSchemaFromCandidate(selCandidate);
          state.bindings[bindingDef.key] = {
            kind: selected.widgetName ? "widget" : selected.inputName ? "input" : selected.outputIndex != null ? "output" : "node",
            nodeId: selected.nodeId,
            nodeType: selected.nodeType,
            nodeTitle: selected.nodeTitle,
            widgetName: selected.widgetName,
            inputName: selected.inputName,
            outputIndex: selected.outputIndex,
            label: selected.nodeTitle || selected.nodeType,
            candidates: selected.candidates || [],
            widgetSchema: selWidgetSchema,
          };
          cancelGraphBinding();
          state.bindingCaptureActive = null;
          renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
        },
      }));
    } else if (!isGraphAvailable() && !state.graphCaptured) {
      row.style.opacity = "0.4";
      row.title = "Graph not available";
    } else {
      row.addEventListener("click", (event) => {
        if (isWizardInteractiveTarget(event)) return;
        startBindingCapture(state, bindingDef);
      });
      row.style.cursor = "pointer";
    }

    // If captured with candidates (more than one option), show a compact dropdown
    if (isBound && bindingValue.candidates && bindingValue.candidates.length > 1) {
      const candidateDropdown = renderCandidateDropdown(bindingValue, bindingDef, state);
      row.appendChild(candidateDropdown);
    }

    list.appendChild(row);
  });

  return list;
}

function renderBoundValue(bindingValue, bindingDef) {
  const pieces = [];
  if (bindingValue.nodeTitle) pieces.push(bindingValue.nodeTitle);
  if (bindingValue.widgetName) pieces.push(`widget: ${bindingValue.widgetName}`);
  else if (bindingValue.inputName) pieces.push(`input: ${bindingValue.inputName}`);
  else if (bindingValue.outputIndex != null) pieces.push(`output #${bindingValue.outputIndex}`);

  return el("span", {
    text: pieces.join(" \u2192 ") || `Node ${bindingValue.nodeId}`,
    style: "color:#4ade80;font-size:10px;",
  });
}

function renderCandidateDropdown(bindingValue, bindingDef, state) {
  const container = el("div", { style: "margin-top:4px;" });
  const select = el("select", {
    class: "comfymodal-studio-select",
    style: "font-size:10px;padding:2px 4px;",
  });
  select.addEventListener("mousedown", (event) => {
    event.stopPropagation();
  });
  select.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  const currentWidget = bindingValue.widgetName;
  const currentInput = bindingValue.inputName;
  const currentOutput = bindingValue.outputIndex;

  bindingValue.candidates.forEach((c) => {
    let isCurrent = false;
    if (c.kind === "widget") isCurrent = c.name === currentWidget;
    else if (c.kind === "input") isCurrent = c.name === currentInput;
    else if (c.kind === "output") isCurrent = c.index === currentOutput;
    else if (c.kind === "node") isCurrent = !currentWidget && !currentInput && currentOutput == null;

    const opt = el("option", {
      value: JSON.stringify({ kind: c.kind, name: c.name, index: c.index }),
      text: `${c.kind}: ${c.label}`,
    });
    if (isCurrent) opt.selected = true;
    select.appendChild(opt);
  });

  select.addEventListener("change", () => {
    try {
      const val = JSON.parse(select.value);
      if (val.kind === "widget") { bindingValue.widgetName = val.name; bindingValue.inputName = null; bindingValue.outputIndex = null; }
      else if (val.kind === "input") { bindingValue.inputName = val.name; bindingValue.widgetName = null; bindingValue.outputIndex = null; }
      else if (val.kind === "output") { bindingValue.outputIndex = val.index; bindingValue.widgetName = null; bindingValue.inputName = null; }
      // Phase 4: keep widgetSchema in sync with the selected candidate
      const updatedCandidate = _findSelectedCandidate(
        bindingValue.candidates,
        { widgetName: bindingValue.widgetName, inputName: bindingValue.inputName, outputIndex: bindingValue.outputIndex }
      );
      bindingValue.widgetSchema = _buildWidgetSchemaFromCandidate(updatedCandidate);
      renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
    } catch { /* ignore parse errors */ }
  });

  container.appendChild(select);
  return container;
}

function isWizardInteractiveTarget(event) {
  const target = event && event.target;
  return !!(target && target.closest && target.closest("select, button, input, textarea, a"));
}

function startBindingCapture(state, bindingDef) {
  cancelGraphBinding(); // Cancel any prior capture

  state.bindingCaptureActive = bindingDef.key;
  renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);

  const cancelFn = beginGraphBindingCapture({
    bindingKey: bindingDef.key,
    label: bindingDef.label,
    onCapture: (result) => {
      // Phase 4: extract widgetSchema from the selected candidate
      const selectedCandidate = _findSelectedCandidate(
        result.candidates,
        { widgetName: result.widgetName, inputName: result.inputName, outputIndex: result.outputIndex }
      );
      const widgetSchema = _buildWidgetSchemaFromCandidate(selectedCandidate);
      state.bindings[result.bindingKey] = {
        kind: result.widgetName ? "widget" : result.inputName ? "input" : result.outputIndex != null ? "output" : "node",
        nodeId: result.nodeId,
        nodeType: result.nodeType,
        nodeTitle: result.nodeTitle,
        widgetName: result.widgetName,
        inputName: result.inputName,
        outputIndex: result.outputIndex,
        label: result.nodeTitle || result.nodeType,
        candidates: result.candidates || [],
        widgetSchema: widgetSchema,
      };
      state.bindingCaptureActive = null;
      renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
    },
    onCancel: (reason) => {
      state.bindingCaptureActive = null;
      renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
    },
  });
}

// ── Step: Details ───────────────────────────────────────────────────────

function renderDetailsStep(body, state) {
  const heading = el("h4", { class: "comfymodal-studio-wizard-section-title", text: "Preset Details" });
  body.appendChild(heading);

  const desc = el("p", {
    class: "comfymodal-studio-wizard-description",
    text: "Name your preset and add an optional description.",
  });
  body.appendChild(desc);

  const form = el("div", { class: "comfymodal-studio-wizard-details-form" });

  // Name
  const nameGroup = el("div", { class: "comfymodal-studio-backend-field" });
  nameGroup.appendChild(el("label", { text: "Preset Name *" }));
  const nameInput = el("input", {
    type: "text",
    value: state.details.name,
    placeholder: "My Amazing Preset",
  });
  nameInput.addEventListener("input", () => {
    state.details.name = nameInput.value;
    const saveBtn = _wizardRoot && _wizardRoot.querySelector('[data-role="save-preset"]');
    if (saveBtn) {
      saveBtn.disabled = !(state.details.name.trim().length > 0 && checkAllRequiredBindings(state) && getComfyGraphContext().ok);
    }
  });
  nameGroup.appendChild(nameInput);
  form.appendChild(nameGroup);

  // Description
  const descGroup = el("div", { class: "comfymodal-studio-backend-field" });
  descGroup.appendChild(el("label", { text: "Description" }));
  const descInput = el("textarea", {
    value: state.details.description,
    placeholder: "Optional description",
    rows: 3,
  });
  descInput.addEventListener("input", () => {
    state.details.description = descInput.value;
  });
  descGroup.appendChild(descInput);
  form.appendChild(descGroup);

  // Binding summary
  const summary = el("div", { style: "margin-top:12px;padding:8px;background:#0a0a0a;border:1px solid #2a2a2a;border-radius:3px;" });
  summary.appendChild(el("p", { text: `Features: ${state.selectedFeatures.join(", ")}`, style: "font-size:11px;color:#888;margin:0 0 4px;" }));
  summary.appendChild(el("p", { text: `Bindings: ${Object.keys(state.bindings).length} configured`, style: "font-size:11px;color:#888;margin:0;" }));
  form.appendChild(summary);

  body.appendChild(form);
}

// ── Step: Saving ────────────────────────────────────────────────────────

function renderSavingStep(body, state) {
  body.appendChild(el("div", { style: "text-align:center;padding:20px;" }, [
    el("p", { text: "Capturing graph and creating preset...", style: "color:#888;font-size:12px;" }),
    el("div", { class: "comfymodal-studio-wizard-spinner" }),
  ]));
}

// ── Step: Saved ─────────────────────────────────────────────────────────

function renderSavedStep(body, state) {
  const isEdit = state.isEdit;
  const presetStatus = state.presetResult ? (state.presetResult.status || "unknown") : (state.existingPreset && state.existingPreset.status) || "unknown";
  const isRunnable = presetStatus === "runnable";
  const success = el("div", { style: "text-align:center;padding:16px;" }, [
    el("div", { text: "\u2713", style: `font-size:32px;color:${isRunnable ? "#4ade80" : "#fbbf24"};` }),
    el("h4", {
      text: isEdit ? "Preset Updated" : (isRunnable ? "Preset Saved" : "Preset Saved With Follow-Up Needed"),
      style: "margin:8px 0;color:#d0d0d0;",
    }),
    el("p", {
      text: isEdit ? `"${state.details.name}" has been updated.` : `"${state.details.name}" has been created.`,
      style: "font-size:12px;color:#888;margin:0 0 8px;",
    }),
  ]);

  // Show status truthfully
  if (state.snapshotResult) {
    success.appendChild(el("p", {
      text: `Snapshot status: ${state.snapshotResult.status || "unknown"}`,
      style: "font-size:11px;color:#888;margin:4px 0;",
    }));
  }
  if (state.presetResult) {
    success.appendChild(el("p", {
      text: `Preset status: ${presetStatus}`,
      style: "font-size:11px;color:#888;margin:4px 0;",
    }));
  }
  if (!isRunnable && !isEdit) {
    const reason = (state.presetResult && state.presetResult.disabledReason) || (state.existingPreset && state.existingPreset.disabledReason) || "";
    success.appendChild(el("p", {
      text: reason || "This preset is saved but not yet runnable.",
      style: "font-size:11px;color:#fbbf24;margin:4px 0;",
    }));
  }

  body.appendChild(success);
}

// ── Step: Error ─────────────────────────────────────────────────────────

function renderErrorStep(body, state) {
  const errorEl = el("div", { style: "text-align:center;padding:16px;" }, [
    el("div", { text: "\u2717", style: "font-size:32px;color:#f87171;" }),
    el("h4", { text: "Failed to Save Preset", style: "margin:8px 0;color:#f87171;" }),
    el("p", { text: state.errorMessage || "An unknown error occurred.", style: "font-size:12px;color:#aaa;margin:0;" }),
  ]);
  body.appendChild(errorEl);
}

// ── Save orchestration ──────────────────────────────────────────────────

async function executeSave(state) {
  state.step = "saving";
  const panel = _wizardRoot && _wizardRoot.querySelector(".comfymodal-studio-wizard-panel");
  if (panel) renderWizard(panel, state);

  const apiBase = state._apiBase;

  try {
    // Build nodeBindings from wizard state
    const nodeBindings = {};
    Object.entries(state.bindings).forEach(([key, val]) => {
      if (val && val.nodeId) {
        nodeBindings[key] = {
          kind: val.kind || "node",
          nodeId: val.nodeId,
          nodeType: val.nodeType || "",
          nodeTitle: val.nodeTitle || "",
        };
        if (val.widgetName) nodeBindings[key].widgetName = val.widgetName;
        if (val.inputName) nodeBindings[key].inputName = val.inputName;
        if (val.outputIndex != null) nodeBindings[key].outputIndex = val.outputIndex;
      }
    });

    const outputNodeId = state.bindings.output && state.bindings.output.nodeId ? state.bindings.output.nodeId : null;

    if (state.isEdit && state.existingSnapshotId) {
      // ── Edit mode: update snapshot bindings + control schemas ──────
      const controlSchemas = buildControlSchemas(state);
      const snapshotUpdate = {
        compatibleFeatures: state.selectedFeatures,
        nodeBindings: nodeBindings,
        controlSchemas: controlSchemas,
      };
      if (outputNodeId) snapshotUpdate.outputNodeId = outputNodeId;

      await updateSnapshot(apiBase, state.existingSnapshotId, snapshotUpdate);

      // ── Update preset metadata ────────────────────────────────────
      if (state.existingPresetId) {
        await updatePreset(apiBase, state.existingPresetId, {
          label: state.details.name,
          description: state.details.description,
          compatibleFeatures: state.selectedFeatures,
          snapshotId: state.existingSnapshotId,
        });
      }

      state.step = "saved";
      return;
    }

    // ── New preset flow ─────────────────────────────────────────────

    // 1. Capture the current graph
    const captureResult = await captureCurrentComfyGraph();
    if (!captureResult.ok) {
      state.step = "error";
      state.errorMessage = captureResult.reason || "Failed to capture graph";
      return;
    }

    state.graphJson = captureResult.graphJson;
    state.apiPromptJson = captureResult.apiPromptJson;
    state.captureWarnings = captureResult.warnings || [];

    // 2. Create snapshot
    const controlSchemas = buildControlSchemas(state);
    const snapshotPayload = {
      name: state.details.name + " (snapshot)",
      description: state.details.description,
      compatibleFeatures: state.selectedFeatures,
      graphJson: state.graphJson,
      apiPromptJson: state.apiPromptJson,
      nodeBindings: nodeBindings,
      outputNodeId: outputNodeId || "",
      source: "current_graph",
      controlSchemas: controlSchemas,
    };

    const snapshotResult = await createSnapshot(apiBase, snapshotPayload);
    if (!snapshotResult || !snapshotResult.snapshot) {
      state.step = "error";
      state.errorMessage = "Server rejected snapshot creation";
      return;
    }

    state.snapshotResult = snapshotResult.snapshot;
    const snapshotId = snapshotResult.snapshot.id;

    // 3. Create preset
    const presetPayload = {
      label: state.details.name,
      description: state.details.description,
      snapshotId: snapshotId,
      compatibleFeatures: state.selectedFeatures,
      defaults: {},
    };

    const presetResult = await createPreset(apiBase, presetPayload);
    if (!presetResult || !presetResult.preset) {
      state.step = "error";
      state.errorMessage = "Server rejected preset creation";
      return;
    }

    state.presetResult = presetResult.preset;

    // 4. Show success
    state.step = "saved";
  } catch (err) {
    state.step = "error";
    state.errorMessage = err.message || "An unexpected error occurred";
  }
}

// ── Phase 4: Build widget schema from a single candidate ────────────

function _buildWidgetSchemaFromCandidate(candidate) {
  /** Extract widget schema metadata from a captured LiteGraph candidate.
   *
   *  Returns null for non-widget candidates (input, output, node).
   *  Fields mirror what extractNodeCandidates captures from LiteGraph widgets.
   */
  if (!candidate || candidate.kind !== "widget") return null;
  return {
    schemaType: candidate.schemaType || null,
    enumValues: candidate.enumValues || null,
    min: candidate.min,
    max: candidate.max,
    step: candidate.step,
    precision: candidate.precision,
    defaultValue: candidate.defaultValue,
    multiline: candidate.multiline || false,
  };
}

function _findSelectedCandidate(candidates, bindingValue) {
  /** Find the candidate matching the current widget/input/output selection. */
  if (!candidates || !bindingValue) return null;
  if (candidates.length === 1) return candidates[0];
  return candidates.find((c) => {
    if (c.kind === "widget") return c.name === bindingValue.widgetName;
    if (c.kind === "input") return c.name === bindingValue.inputName;
    if (c.kind === "output") return c.index === bindingValue.outputIndex;
    return false;
  }) || null;
}

// ── Phase 4: Build control schemas from bound widget data ────────────

function buildControlSchemas(state) {
  /** Build a controlSchemas dict keyed by control (binding) ID.
   *
   *  Each entry is a schema dict captured from the live LiteGraph widget
   *  metadata.  This is persisted with the snapshot and takes priority
   *  over the Python-side static registry at runtime.
   *
   *  Only widget-kind bindings with captured widgetSchema contribute.
   *  Node/input/output bindings without widget metadata are omitted.
   */
  const schemas = {};
  Object.entries(state.bindings).forEach(([key, val]) => {
    if (!val || !val.nodeId) return;
    const ws = val.widgetSchema;
    if (!ws) return;
    if (val.kind !== "widget") return;

    const schema = {
      kind: mapSchemaKind(ws),
      nodeId: val.nodeId,
      nodeType: val.nodeType || "",
      widgetName: val.widgetName || "",
      default: ws.defaultValue,
    };

    if (ws.schemaType === "enum" && ws.enumValues) {
      schema.options = ws.enumValues;
    }
    if (ws.min != null) schema.minimum = ws.min;
    if (ws.max != null) schema.maximum = ws.max;
    if (ws.step != null) schema.step = ws.step;
    if (ws.precision != null) schema.precision = ws.precision;
    if (ws.multiline) schema.multiline = true;

    schemas[key] = schema;
  });
  return schemas;
}

function mapSchemaKind(ws) {
  if (!ws || !ws.schemaType) return "unresolved";
  if (ws.schemaType === "enum") return "enum";
  if (ws.schemaType === "number") return "number";
  if (ws.schemaType === "integer") return "integer";
  if (ws.schemaType === "boolean") return "boolean";
  if (ws.multiline) return "multiline";
  return ws.schemaType;
}

// ── Helpers ─────────────────────────────────────────────────────────────

function collectRequiredBindings(featureIds) {
  const bindings = [];
  const seen = new Set();
  featureIds.forEach((fid) => {
    const def = FEATURE_DEFS[fid];
    if (def) {
      def.requiredBindings.forEach((b) => {
        if (!seen.has(b.key)) {
          seen.add(b.key);
          bindings.push(b);
        }
      });
    }
  });
  return bindings;
}

function collectRequiredAndOptionalBindings(featureIds) {
  const bindings = [];
  const seen = new Set();
  featureIds.forEach((fid) => {
    const def = FEATURE_DEFS[fid];
    if (def) {
      def.requiredBindings.forEach((b) => {
        if (!seen.has(b.key)) {
          seen.add(b.key);
          bindings.push({ ...b, required: true });
        }
      });
      def.optionalBindings.forEach((b) => {
        if (!seen.has(b.key)) {
          seen.add(b.key);
          bindings.push({ ...b, required: false });
        }
      });
    }
  });
  return bindings;
}

function checkAllRequiredBindings(state) {
  const required = collectRequiredBindings(state.selectedFeatures);
  return required.every((b) => {
    const val = state.bindings[b.key];
    return val && val.nodeId;
  });
}

function closePresetWizardAndNotify() {
  const onDone = _wizardState ? _wizardState._onDone : null;
  closePresetWizard();
  if (onDone) onDone();
}

// ── Exported for test access ────────────────────────────────────────────

export { FEATURE_DEFS, makeInitialState, collectRequiredBindings, checkAllRequiredBindings };
