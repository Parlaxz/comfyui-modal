// Modal Studio — Preset Wizard
//
// Side-panel wizard for creating a Studio preset from the current ComfyUI graph.
// Steps: features → bindings → details → saving/saved/error.
// Wires into studio-backend.js as the primary "Make Preset" flow.

import { el } from "./studio-ui.js";
import {
  isGraphAvailable,
  getComfyGraphContext,
  beginGraphBindingCapture,
  cancelGraphBinding,
  getSelectedGraphNodeTarget,
} from "./studio-graph-binding.js";
import { captureCurrentComfyGraph } from "./studio-backend-capture.js";
import { createSnapshot, createPreset } from "./studio-backend-api.js";

// ── Feature definitions with required binding specs ─────────────────────

const FEATURE_DEFS = {
  txt2img: {
    id: "txt2img",
    label: "Txt2Img",
    description: "Standard text-to-image generation",
    requiredBindings: [
      { key: "prompt", label: "Prompt", description: "The text prompt widget/input" },
      { key: "output", label: "Output Image", description: "The image output node" },
    ],
    optionalBindings: [
      { key: "seed", label: "Seed", description: "Seed control (optional)" },
      { key: "steps", label: "Steps", description: "Steps control (optional)" },
    ],
    outputRequired: true,
  },
  object_remove: {
    id: "object_remove",
    label: "Object Remove",
    description: "Remove an object from an image",
    requiredBindings: [
      { key: "source_image", label: "Source Image", description: "Input image node" },
      { key: "mask", label: "Mask", description: "Mask indicating the object to remove" },
      { key: "instruction", label: "Instruction", description: "Prompt describing the removal" },
      { key: "output", label: "Output Image", description: "The image output node" },
    ],
    optionalBindings: [
      { key: "seed", label: "Seed", description: "Seed control (optional)" },
    ],
    outputRequired: true,
  },
  object_replace: {
    id: "object_replace",
    label: "Object Replace",
    description: "Replace an object in an image",
    requiredBindings: [
      { key: "source_image", label: "Source Image", description: "Input image node" },
      { key: "mask", label: "Mask", description: "Mask indicating the object to replace" },
      { key: "replacement_prompt", label: "Replacement Prompt", description: "Prompt describing the replacement" },
      { key: "output", label: "Output Image", description: "The image output node" },
    ],
    optionalBindings: [
      { key: "seed", label: "Seed", description: "Seed control (optional)" },
    ],
    outputRequired: true,
  },
};

// ── Wizard state ────────────────────────────────────────────────────────

let _wizardState = null;
let _wizardRoot = null;

function makeInitialState() {
  return {
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
  };
}

// ── Public API ───────────────────────────────────────────────────────────

export function openPresetWizard(onDone, apiBase) {
  closePresetWizard(); // Clean up any existing wizard first

  _wizardState = makeInitialState();
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
}

// ── Render helpers ──────────────────────────────────────────────────────

function renderWizard(panel, state) {
  while (panel.firstChild) panel.removeChild(panel.firstChild);

  // Header
  const header = el("div", { class: "comfymodal-studio-wizard-header" }, [
    el("h3", { text: "Make Preset", class: "comfymodal-studio-wizard-title" }),
    el("button", {
      class: "comfymodal-studio-wizard-close",
      text: "\u00d7",
      onclick: () => closePresetWizardAndNotify(),
    }),
  ]);
  panel.appendChild(header);

  // Step indicator
  const stepNames = ["Features", "Bindings", "Details"];
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

  // Body
  const body = el("div", { class: "comfymodal-studio-wizard-body" });
  panel.appendChild(body);

  // Graph availability banner
  const graphContext = getComfyGraphContext();
  if (!graphContext.ok) {
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

  // Footer
  const footer = el("div", { class: "comfymodal-studio-wizard-footer" });
  if (state.step === "features") {
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      text: "Continue to Bindings",
      disabled: state.selectedFeatures.length !== 1,
      onclick: () => {
        if (state.selectedFeatures.length !== 1) return;
        state.step = "bindings";
        renderWizard(panel, state);
      },
    }));
  } else if (state.step === "bindings") {
    const allBound = checkAllRequiredBindings(state) && graphContext.ok;
    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: "Back to Features",
      onclick: () => {
        state.step = "features";
        renderWizard(panel, state);
      },
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      text: "Continue to Details",
      disabled: !allBound,
      onclick: () => {
        if (!allBound) return;
        state.step = "details";
        renderWizard(panel, state);
      },
    }));
  } else if (state.step === "details") {
    const canSave = state.details.name.trim().length > 0 && checkAllRequiredBindings(state) && graphContext.ok;
    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: "Back to Bindings",
      onclick: () => {
        state.step = "bindings";
        renderWizard(panel, state);
      },
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      "data-role": "save-preset",
      text: "Save Preset",
      disabled: !canSave,
      onclick: async () => {
        // Check state directly — closure variable is stale from render time
        if (!(state.details.name.trim().length > 0 && checkAllRequiredBindings(state) && getComfyGraphContext().ok)) return;
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
      text: "Make Another",
      onclick: () => {
        closePresetWizard();
        openPresetWizard(state._onDone, state._apiBase);
      },
    }));
  } else if (state.step === "error") {
    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: "Back to Details",
      onclick: () => {
        state.step = "details";
        renderWizard(panel, state);
      },
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-destructive-btn",
      text: "Cancel",
      onclick: () => closePresetWizardAndNotify(),
    }));
  }
  panel.appendChild(footer);
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

  // Collect all bindings for selected features
  const allBindings = collectRequiredAndOptionalBindings(state.selectedFeatures);

  const bindingList = el("div", { class: "comfymodal-studio-wizard-binding-list" });

  const graphContext = getComfyGraphContext();
  bindingList.appendChild(el("div", { class: "comfymodal-studio-wizard-binding-row" + (graphContext.ok ? " bound" : "") }, [
    el("div", { class: "comfymodal-studio-wizard-binding-info" }, [
      el("strong", { style: "font-size:12px;", text: "API Graph" }),
      el("p", { style: "font-size:10px;color:#888;margin:2px 0 0;", text: graphContext.ok ? "Captured from the current ComfyUI graph when you save." : (graphContext.reason || "Graph unavailable") }),
    ]),
    el("div", { class: "comfymodal-studio-wizard-binding-status" }, [
      el("span", { text: graphContext.ok ? "Ready to capture on save" : "Unavailable", style: `font-size:10px;color:${graphContext.ok ? "#4ade80" : "#f87171"};` }),
    ]),
  ]));

  allBindings.forEach((bindingDef) => {
    const bindingValue = state.bindings[bindingDef.key];
    const isBound = Boolean(bindingValue && bindingValue.nodeId);
    const isCaptureActive = state.bindingCaptureActive === bindingDef.key;

    const row = el("div", {
      class: "comfymodal-studio-wizard-binding-row"
        + (isBound ? " bound" : "")
        + (isCaptureActive ? " capturing" : ""),
    }, [
      el("div", { class: "comfymodal-studio-wizard-binding-info" }, [
        el("strong", { style: "font-size:12px;", text: bindingDef.label }),
        el("p", { style: "font-size:10px;color:#888;margin:2px 0 0;", text: bindingDef.description }),
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
      row.addEventListener("click", () => {
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
          };
          cancelGraphBinding();
          state.bindingCaptureActive = null;
          renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
        },
      }));
    } else if (!isGraphAvailable()) {
      row.style.opacity = "0.4";
      row.title = "Graph not available";
    } else {
      row.addEventListener("click", () => {
        // If we have a selected-node fallback button, show it
        startBindingCapture(state, bindingDef);
      });
      row.style.cursor = "pointer";
    }

    // If captured with candidates (more than one option), show a compact dropdown
    if (isBound && bindingValue.candidates && bindingValue.candidates.length > 1) {
      const candidateDropdown = renderCandidateDropdown(bindingValue, bindingDef, state);
      row.appendChild(candidateDropdown);
    }

    bindingList.appendChild(row);
  });

  body.appendChild(bindingList);

  // Binding summary
  const requiredKeys = collectRequiredBindings(state.selectedFeatures).map((b) => b.key);
  const boundCount = requiredKeys.filter((k) => state.bindings[k] && state.bindings[k].nodeId).length;
  const summary = el("p", {
    style: "font-size:11px;color:#888;margin-top:8px;",
    text: `${boundCount} of ${requiredKeys.length} required bindings complete • API graph ${graphContext.ok ? "ready" : "unavailable"}`,
  });
  body.appendChild(summary);
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
      renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
    } catch { /* ignore parse errors */ }
  });

  container.appendChild(select);
  return container;
}

function startBindingCapture(state, bindingDef) {
  cancelGraphBinding(); // Cancel any prior capture

  state.bindingCaptureActive = bindingDef.key;
  renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);

  const cancelFn = beginGraphBindingCapture({
    bindingKey: bindingDef.key,
    label: bindingDef.label,
    onCapture: (result) => {
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
  const presetStatus = state.presetResult ? (state.presetResult.status || "unknown") : "unknown";
  const isRunnable = presetStatus === "runnable";
  const success = el("div", { style: "text-align:center;padding:16px;" }, [
    el("div", { text: "\u2713", style: `font-size:32px;color:${isRunnable ? "#4ade80" : "#fbbf24"};` }),
    el("h4", { text: isRunnable ? "Preset Saved" : "Preset Saved With Follow-Up Needed", style: "margin:8px 0;color:#d0d0d0;" }),
    el("p", { text: `"${state.details.name}" has been created.`, style: "font-size:12px;color:#888;margin:0 0 8px;" }),
  ]);

  // Show server-returned status truthfully
  if (state.snapshotResult) {
    const snapStatus = state.snapshotResult.status || "unknown";
    success.appendChild(el("p", {
      text: `Snapshot status: ${snapStatus}`,
      style: "font-size:11px;color:#888;margin:4px 0;",
    }));
  }
  if (state.presetResult) {
    success.appendChild(el("p", {
      text: `Preset status: ${presetStatus}`,
      style: "font-size:11px;color:#888;margin:4px 0;",
    }));
    if (!isRunnable) {
      success.appendChild(el("p", {
        text: state.presetResult.disabledReason || "This preset is saved but not yet runnable.",
        style: "font-size:11px;color:#fbbf24;margin:4px 0;",
      }));
    }
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

    const outputNodeId = state.bindings.output && state.bindings.output.nodeId ? state.bindings.output.nodeId : "";

    // 2. Create snapshot
    const snapshotPayload = {
      name: state.details.name + " (snapshot)",
      description: state.details.description,
      compatibleFeatures: state.selectedFeatures,
      graphJson: state.graphJson,
      apiPromptJson: state.apiPromptJson,
      nodeBindings: nodeBindings,
      outputNodeId: outputNodeId || "",
      source: "current_graph",
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
