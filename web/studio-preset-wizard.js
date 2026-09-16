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
  viewGraphNode,
  isGraphNodeAvailable,
  clearNodeViewHighlight,
  findCanvasNodeTargets,
} from "./studio-graph-binding.js";
import { captureCurrentComfyGraph } from "./studio-backend-capture.js";
import {
  applyDependencyInflightBadge,
  applyDependencyStateBadge,
  buildManagerPackIndex,
  matchManagerModel,
  normalizeManagerSavePath,
  performManagerInstall,
  renderDependencySection,
} from "./studio-model-library.js";
import {
  createSnapshot,
  createPreset,
  updateSnapshot,
  updatePreset,
  getWorkflowVersion,
  createMapping,
  getVersionDependencies,
  batchInstallModels,
  rescanModels,
  refreshCustomNodes,
  getManagerVersion,
  listManagerInstalled,
  managerRebootAndWait,
  getManagerModels,
  getManagerPackList,
  getManagerMappings,
  WIZARD_DRAFT_KEY,
  WIZARD_DRAFT_MAX_CHARS,
  buildWizardDraft,
  parseWizardDraft,
  applyWizardDraft,
} from "./studio-backend-api.js";
import {
  BINDABLE_INPUTS,
  OUTPUT_BINDING,
  T2I_REQUIRED_INPUTS,
  T2I_OPTIONAL_INPUTS,
} from "./studio-bindable-inputs.js";

// ── Catalog-backed feature definitions ───────────────────────────────────
// Leaf 1.2.1 follow-up: the wizard lists ONLY the code-owned bindable-input
// catalog (Prompt, Seed, Step count, CFG scale, Sampler, Model UNET, VAE,
// CLIP) plus the separate required Output binding. Graph inputs outside the
// catalog are ignored everywhere: they get no row, no suggestion, and never
// satisfy the save gate.
//
// The single Text-to-Image profile is the only workflow type in this slice.
// "txt2img" is the server-facing feature id; "t2i" is accepted as an alias
// wherever feature ids are resolved so older/newer records agree.

function _catalogBindingDef(key) {
  if (key === OUTPUT_BINDING.key) {
    return {
      key: OUTPUT_BINDING.key,
      label: OUTPUT_BINDING.name,
      helpText: "The image output node that produces the result. Bind its exact output field.",
      catalogKey: OUTPUT_BINDING.key,
      isOutput: true,
    };
  }
  const entry = BINDABLE_INPUTS[key];
  if (!entry) return null;
  return {
    key: entry.key,
    label: entry.name,
    helpText: _catalogHelpText(entry),
    catalogKey: entry.key,
    block: entry.block,
    isOutput: false,
  };
}

function _catalogHelpText(entry) {
  const hints = {
    prompt: "Bind the exact prompt text widget/field.",
    seed: "Bind the exact seed widget/field.",
    step_count: "Bind the exact step-count widget/field.",
    cfg_scale: "Bind the exact CFG-scale widget/field.",
    sampler: "Bind the exact sampler widget/field.",
    model_unet: "Bind the exact UNET model widget/field.",
    vae: "Bind the exact VAE widget/field.",
    clip: "Bind the exact CLIP widget/field.",
  };
  return hints[entry.key] || `Bind the exact ${entry.name} widget/field.`;
}

const FEATURE_DEFS = {
  txt2img: {
    id: "txt2img",
    label: "Text-to-Image",
    description: "Standard text-to-image generation",
    requiredBindings: [...T2I_REQUIRED_INPUTS, OUTPUT_BINDING.key]
      .map(_catalogBindingDef)
      .filter(Boolean),
    optionalBindings: [...T2I_OPTIONAL_INPUTS]
      .map(_catalogBindingDef)
      .filter(Boolean),
  },
};

function _normalizeFeatureId(fid) {
  if (fid === "t2i" || fid === "txt2img") return "txt2img";
  return fid;
}

function _featureDef(featureId) {
  return FEATURE_DEFS[_normalizeFeatureId(featureId)] || null;
}

// T2I save gate: every one of these roles needs a valid concrete binding
// (exact node widget/field, user-confirmed) before save is allowed.
const T2I_SAVE_GATE_KEYS = Object.freeze([...T2I_REQUIRED_INPUTS, OUTPUT_BINDING.key]);

// ── Likely-target suggestions ─────────────────────────────────────────────
// Static per-role hints (node type → widget/field) shown on unbound rows so
// the user knows where to look. Graph-backed suggestions (below) only ever
// propose; the user confirms the exact node widget/field with an explicit
// click — nothing is ever auto-bound.

const ROLE_SUGGESTIONS = Object.freeze({
  prompt: Object.freeze([{ nodeType: "CLIPTextEncode", widget: "text" }]),
  seed: Object.freeze([{ nodeType: "KSampler", widget: "seed" }]),
  step_count: Object.freeze([{ nodeType: "KSampler", widget: "steps" }]),
  cfg_scale: Object.freeze([{ nodeType: "KSampler", widget: "cfg" }]),
  sampler: Object.freeze([{ nodeType: "KSampler", widget: "sampler_name" }]),
  model_unet: Object.freeze([
    { nodeType: "UNETLoader", widget: "unet_name" },
    { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" },
  ]),
  vae: Object.freeze([
    { nodeType: "VAELoader", widget: "vae_name" },
    { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" },
  ]),
  clip: Object.freeze([
    { nodeType: "CLIPLoader", widget: "clip_name" },
    { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" },
  ]),
  output: Object.freeze([
    { nodeType: "SaveImage", output: "images" },
    { nodeType: "PreviewImage", output: "images" },
  ]),
});

function _graphNodes(graphJson) {
  if (!graphJson) return [];
  if (Array.isArray(graphJson)) return graphJson;
  if (Array.isArray(graphJson.nodes)) return graphJson.nodes;
  return [];
}

function _nodeTypeOf(node) {
  return (node && (node.class_type || node.type)) || "";
}

function _nodeTitleOf(node) {
  if (!node) return "";
  return node.title || _nodeTypeOf(node) || `Node ${node.id}`;
}

/**
 * Suggest likely graph targets for one catalog role.
 * Pure: scans the given graph JSON for nodes matching the role's known
 * node types and returns concrete {nodeId, nodeType, nodeTitle,
 * widgetName/inputName/outputIndex} proposals. Non-catalog roles and graph
 * nodes outside the catalog patterns yield [] — they are ignored.
 * Suggestions are proposals only; callers must get explicit user
 * confirmation before storing one as a binding.
 */
export function suggestBindingTargets(graphJson, roleKey) {
  const patterns = ROLE_SUGGESTIONS[roleKey];
  if (!patterns) return [];
  const out = [];
  _graphNodes(graphJson).forEach((node) => {
    if (!node) return;
    const nodeType = _nodeTypeOf(node);
    patterns.forEach((pattern) => {
      if (nodeType !== pattern.nodeType) return;
      if (pattern.widget) {
        out.push({
          nodeId: node.id,
          nodeType,
          nodeTitle: _nodeTitleOf(node),
          widgetName: pattern.widget,
          inputName: null,
          outputIndex: null,
        });
      } else if (pattern.output) {
        const outputs = Array.isArray(node.outputs) ? node.outputs : [];
        let outputIndex = 0;
        const named = outputs.findIndex((o) => o && (o.name === pattern.output || o.type === pattern.output));
        if (named !== -1) outputIndex = named;
        out.push({
          nodeId: node.id,
          nodeType,
          nodeTitle: _nodeTitleOf(node),
          widgetName: null,
          inputName: null,
          outputIndex,
        });
      }
    });
  });
  return out;
}

/** Suggest targets for every catalog role + output; non-catalog roles never appear. */
export function suggestAllBindings(graphJson) {
  const out = {};
  [...Object.keys(BINDABLE_INPUTS), OUTPUT_BINDING.key].forEach((key) => {
    out[key] = suggestBindingTargets(graphJson, key);
  });
  return out;
}

function _likelyTargetHint(roleKey) {
  const patterns = ROLE_SUGGESTIONS[roleKey];
  if (!patterns || !patterns.length) return "";
  const first = patterns[0];
  const target = first.widget ? first.widget : first.output ? `output ${first.output}` : "";
  return `Likely: ${first.nodeType} → ${target}`;
}

/**
 * True only for a valid concrete binding: an exact node plus the confirmed
 * widget/input/output field. A nodeId alone (e.g. from an unconfirmed
 * suggestion) never satisfies the save gate.
 */
export function isValidConcreteBinding(val) {
  if (!val || val.nodeId == null) return false;
  return !!(val.widgetName || val.inputName || val.outputIndex != null);
}

// ── Wizard state ────────────────────────────────────────────────────────

let _wizardState = null;
let _wizardRoot = null;

function makeInitialState(existingPreset, existingSnapshot, options) {
  const state = {
    step: "features",           // features | bindings | details | saving | saved | error
    selectedFeatures: [],
    bindings: {},               // { [bindingKey]: bindingTarget | null }
    bindingCaptureActive: null, // bindingKey currently being captured, or null
    captureNotice: null, // { key, message } when a capture found no bindable fields
    viewNotice: null, // { key, message } when View found no node to highlight
    details: {
      name: "",
      description: "",
    },
    graphCaptured: false,
    graphJson: null,
    apiPromptJson: null,
    captureWarnings: [],
    // Dependencies step (version-setup mode only)
    dependencies: null,
    dependenciesBusy: false,
    dependenciesMessage: "",
    managerProbed: false,
    managerProbing: false,
    managerDetected: null,
    managerInstalled: [],
    managerModelsByFilename: null,
    managerPacks: null,
    installingPack: null,
    restartRequired: false,
    rebootInFlight: false,
    // Explicit per-row install status lives in wizard state (not just DOM) so
    // a re-render — e.g. the Manager probe finishing or a dependency refresh —
    // can never drop an in-flight model/pack row's queued/downloading status.
    modelInstalls: {},  // report model key -> "Queued" | "Downloading…"
    nodeInstalls: {},   // custom-node name -> "Queued"
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

  // ── Workflow-version setup mode (leaf 1.2.1) ────────────────────────
  // Bound to one unmapped workflow version. The step flow, T2I save gate,
  // suggestions, and explicit confirmation are identical to preset mode,
  // but save persists a version mapping through the existing mapping POST
  // route — never a Backend snapshot or preset — and no Backend/Preset
  // concepts appear in copy or navigation.
  const versionOpt = (options && typeof options === "object") ? options : {};
  if (versionOpt.workflowVersionId) {
    state.isVersionSetup = true;
    state.workflowId = versionOpt.workflowId || "";
    state.workflowVersionId = versionOpt.workflowVersionId;
  }

  return state;
}

// QoL: while the wizard is open the modal header reads "Workflow Setup
// wizard" instead of "Modal GPU"; restored on close. Null-safe for hosts
// without the shell heading (e.g. focused test mounts).
function _setStudioHeaderWizardMode(on) {
  try {
    const heading = document.getElementById("comfymodal-studio-heading");
    if (heading) heading.textContent = on ? "Workflow Setup wizard" : "Modal GPU";
  } catch (e) { /* non-DOM host */ }
}

// ── Public API ───────────────────────────────────────────────────────────

export function openPresetWizard(onDone, apiBase, existingPreset, existingSnapshot, options) {
  closePresetWizard({ keepDraft: true }); // Clean up any existing wizard first

  _wizardState = makeInitialState(existingPreset, existingSnapshot, options);
  _wizardState._onDone = onDone;
  _wizardState._apiBase = apiBase || "/comfymodal";

  // Browser refresh/reload: resume the same workflow/version wizard at the
  // step (and bindings/details) it was left on. Identity is re-checked inside
  // applyWizardDraft, so a draft for another version is ignored, not applied.
  if (_wizardState.isVersionSetup) {
    const draft = readWizardDraft();
    if (draft) applyWizardDraft(_wizardState, draft, _wizardStepKeys(_wizardState));
  }

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
  _setStudioHeaderWizardMode(true);

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

  // Version-setup mode: pre-seed suggestions from the version's stored
  // graph so the wizard is usable without the live ComfyUI graph, and load
  // the dependency report so the Dependencies step can be validated first.
  if (_wizardState.isVersionSetup) {
    prefetchVersionSetupGraph(_wizardState);
    prefetchVersionDependencies(_wizardState);
  }

  // Notify modal layer that wizard is opening so it can release
  // background inertness (blocked by _inertBackground(true) in
  // open_testing_modal). The wizard's graph binding capture
  // (beginGraphBindingCapture) needs the underlying ComfyUI graph
  // clickable — inert on ancestors blocks all pointer events.
  document.dispatchEvent(new CustomEvent("comfymodal:wizard-opening"));
}

export function closePresetWizard(options) {
  const keepDraft = !!(options && options.keepDraft);
  // Clean up graph binding capture + transient node highlight
  cancelGraphBinding();
  clearNodeViewHighlight();

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
  _setStudioHeaderWizardMode(false);

  if (_wizardRoot && _wizardRoot.parentNode) {
    _wizardRoot.parentNode.removeChild(_wizardRoot);
  }

  // Done/close clears the persisted draft + URL marker; the internal cleanup
  // at the start of openPresetWizard keeps it (keepDraft) so reopening the
  // same wizard — e.g. after a reboot reload — still resumes in place.
  if (!keepDraft) clearWizardDraft();

  _wizardRoot = null;
  _wizardState = null;

  // Notify modal layer that wizard has closed so it can restore
  // background inertness (if the parent modal is still open).
  document.dispatchEvent(new CustomEvent("comfymodal:wizard-closed"));
}

// ── Render helpers ──────────────────────────────────────────────────────

// Step ordering. The Dependencies step is always woven into version-setup
// mode as step 2 (features → dependencies → bindings → details) so validation
// happens before bindings & controls. Preset/edit modes without a bound
// version keep the original features → bindings → details path. Continue is
// always available on the Dependencies step, so it never becomes a trap.
function _wizardStepKeys(state) {
  const includeDeps = !!(state && state.isVersionSetup);
  return includeDeps
    ? ["features", "dependencies", "bindings", "details"]
    : ["features", "bindings", "details"];
}

function _wizardStepLabel(key) {
  if (key === "features") return "Feature Type";
  if (key === "dependencies") return "Dependencies";
  if (key === "bindings") return "Bindings & Controls";
  return "Details";
}

// ── Setup-wizard draft persistence (namespaced, bounded) ─────────────────
//
// A browser refresh must reopen the SAME workflow/version wizard at the SAME
// step. The bounded draft schema is owned by studio-backend-api.js (pure and
// unit-tested there); this module owns the sessionStorage + URL-marker side
// effects. Version-setup mode only — preset/edit wizards opened from other
// pages are neither persisted nor resumed, so unrelated pages stay untouched.

const WIZARD_URL_PARAM = "comfymodal_wizard";

function _wizardHashHasMarker(hash) {
  return typeof hash === "string" && hash.indexOf(WIZARD_URL_PARAM + "=") !== -1;
}

/** Add/remove the namespaced marker on an existing Studio hash. Best-effort. */
function _syncWizardUrlMarker(on) {
  try {
    if (typeof window === "undefined" || !window.location || typeof history === "undefined") return;
    const loc = window.location;
    const hash = loc.hash || "";
    // Never manage an unrelated (non-Studio) host hash.
    if (!/^#?comfymodal=/.test(hash)) return;
    const has = _wizardHashHasMarker(hash);
    if (on === has) return;
    let next;
    if (on) {
      next = hash + "&" + WIZARD_URL_PARAM + "=1";
    } else {
      next = hash
        .replace(new RegExp("([#&])" + WIZARD_URL_PARAM + "=1"), "$1")
        .replace(/[#&]$/, "");
    }
    history.replaceState(history.state, "", loc.pathname + loc.search + next);
  } catch (e) { /* URL marker is best-effort */ }
}

/** Store the bounded draft in sessionStorage + mark the Studio URL. */
function saveWizardDraft(state) {
  if (!state || !state.isVersionSetup) return;
  const draft = buildWizardDraft(state);
  if (!draft) return;
  try {
    const text = JSON.stringify(draft);
    if (text.length <= WIZARD_DRAFT_MAX_CHARS && typeof sessionStorage !== "undefined") {
      sessionStorage.setItem(WIZARD_DRAFT_KEY, text);
    }
  } catch (e) { /* storage unavailable/full: draft is best-effort */ }
  _syncWizardUrlMarker(true);
}

/** Read + validate the bounded draft. Null when absent/malformed/stale. */
export function readWizardDraft() {
  try {
    if (typeof sessionStorage === "undefined") return null;
    return parseWizardDraft(sessionStorage.getItem(WIZARD_DRAFT_KEY));
  } catch (e) { return null; }
}

/**
 * True when the current Studio URL carries the draft marker. A real browser
 * reload preserves it; an in-app shell navigation rewrites the hash and drops
 * it — so only reloads auto-reopen the wizard.
 */
export function hasWizardUrlMarker() {
  try {
    if (typeof window === "undefined" || !window.location) return false;
    return _wizardHashHasMarker(window.location.hash || "");
  } catch (e) { return false; }
}

/** Drop the draft + URL marker after Done/close/save. */
export function clearWizardDraft() {
  try {
    if (typeof sessionStorage !== "undefined") sessionStorage.removeItem(WIZARD_DRAFT_KEY);
  } catch (e) { /* best-effort */ }
  _syncWizardUrlMarker(false);
}

function renderWizard(panel, state) {
  const scrollTop = panel.scrollTop;
  while (panel.firstChild) panel.removeChild(panel.firstChild);
  // The View highlight lives on document.body (outside the wizard DOM), so
  // clear it explicitly whenever the wizard re-renders.
  clearNodeViewHighlight();

  // Header
  const headerTitle = state.isVersionSetup ? "Set up Workflow" : state.isEdit ? "Edit Preset" : "Make Preset";
  const header = el("div", { class: "comfymodal-studio-wizard-header" }, [
    el("h3", { text: headerTitle, class: "comfymodal-studio-wizard-title" }),
    el("button", {
      class: "comfymodal-secondary-btn comfymodal-studio-wizard-back",
      text: "Back to Modal Studio",
      "data-testid": "wizard-back-to-studio",
      style: "width:auto;padding:4px 10px;font-size:11px;",
      onclick: () => closePresetWizardAndNotify(),
    }),
    el("button", {
      class: "comfymodal-studio-wizard-close",
      text: "×",
      onclick: () => closePresetWizardAndNotify(),
    }),
  ]);
  panel.appendChild(header);

  // Step indicator (skip in edit mode — edit starts at bindings)
  if (!state.isEdit) {
    const stepKeys = _wizardStepKeys(state);
    const stepNames = stepKeys.map(_wizardStepLabel);

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
    case "dependencies":
      renderDependenciesStep(body, state);
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
  const includeDeps = !!state.isVersionSetup;
  const footer = el("div", { class: "comfymodal-studio-wizard-footer" });
  if (state.step === "features") {
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      "data-testid": "wizard-features-continue",
      text: includeDeps ? "Continue to Dependencies" : "Continue to Bindings",
      disabled: state.selectedFeatures.length !== 1,
      onclick: () => {
        if (state.selectedFeatures.length !== 1) return;
        navigateStep(includeDeps ? "dependencies" : "bindings");
      },
    }));
  } else if (state.step === "dependencies") {
    // Validation aid, never a trap: Continue is always available because
    // some models legitimately have no source URL and some packs have no
    // repository to install from.
    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "wizard-dependencies-back",
      text: "Back to Features",
      onclick: () => navigateStep("features"),
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      "data-testid": "wizard-dependencies-continue",
      text: "Continue to Bindings",
      onclick: () => navigateStep("bindings"),
    }));
  } else if (state.step === "bindings") {
    const allRequiredBound = checkAllRequiredBindings(state);
    const graphOk = graphContext.ok || state.graphCaptured;

    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: state.isEdit ? "Cancel" : (includeDeps ? "Back to Dependencies" : "Back to Features"),
      onclick: () => {
        if (state.isEdit) {
          closePresetWizardAndNotify();
        } else {
          navigateStep(includeDeps ? "dependencies" : "features");
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
    const graphReady = getComfyGraphContext().ok || state.graphCaptured;
    const canSave = state.isVersionSetup
      ? checkAllRequiredBindings(state) && graphReady
      : state.details.name.trim().length > 0 && checkAllRequiredBindings(state) && graphReady;
    footer.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      text: "Back to Bindings",
      onclick: () => navigateStep("bindings"),
    }));
    footer.appendChild(el("button", {
      class: "comfymodal-primary-btn",
      "data-role": state.isVersionSetup ? "save-setup" : "save-preset",
      "data-testid": state.isVersionSetup ? "wizard-version-save" : "wizard-preset-save",
      text: state.isVersionSetup ? "Save Setup" : state.isEdit ? "Update Preset" : "Save Preset",
      disabled: !canSave,
      onclick: async () => {
        if (!canSave) return;
        await executeSave(state);
        renderWizard(panel, state);
      },
    }));
  } else if (state.step === "saved") {
    if (state.isVersionSetup) {
      footer.appendChild(el("button", {
        class: "comfymodal-primary-btn",
        "data-testid": "wizard-version-done",
        text: "Back to Workflow",
        onclick: () => {
          closePresetWizardAndNotify();
        },
      }));
    } else {
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
    }
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

  // Persist the current step/bindings/details for a version-setup wizard so a
  // browser refresh resumes here; Done/save clears it. `saving` is transient
  // and an `error` step keeps the last good draft, so a refresh returns to the
  // details step rather than a dead-end error screen.
  if (state.isVersionSetup) {
    if (state.step === "saved") {
      clearWizardDraft();
    } else if (state.step === "features" || state.step === "dependencies"
      || state.step === "bindings" || state.step === "details") {
      saveWizardDraft(state);
    }
  }
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

  // Surface the stored-graph prefetch result here too (same testid as the
  // bindings step; only one step renders at a time). The prefetch runs on
  // open for version-setup mode, so the status is already visible before
  // the user picks a feature.
  if (state.suggestStatus) {
    body.appendChild(el("p", {
      "data-testid": "wizard-suggest-status",
      style: "font-size:10px;color:#888;margin:4px 0 0;",
      text: state.suggestStatus,
    }));
  }

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
          ? (state.isVersionSetup
            ? "Uses this workflow version's stored graph."
            : "Captured automatically from the current ComfyUI graph when you save.")
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

  // ── Required bindings (catalog only) ──────────────────────────────
  const featureId = state.selectedFeatures[0];
  const featureDef = featureId ? _featureDef(featureId) : null;
  const requiredDefs = featureDef ? featureDef.requiredBindings : [];
  const optionalDefs = featureDef ? featureDef.optionalBindings : [];

  // ── Suggest-from-graph ─────────────────────────────────────────────
  // Proposes likely graph targets per catalog role. Suggestions never bind
  // anything by themselves — each one needs an explicit user click on its
  // "Use suggestion" button (the exact node widget/field confirmation).
  const suggestWrap = el("div", { style: "margin:12px 0 4px;" });
  const suggestBtn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "wizard-suggest-button",
    text: state.suggestedTargets ? "Re-scan current graph" : "Suggest from current graph",
    style: "width:auto;padding:4px 10px;font-size:11px;",
    onclick: async (event) => {
      event.preventDefault();
      event.stopPropagation();
      suggestBtn.disabled = true;
      try {
        const captureResult = await captureCurrentComfyGraph();
        if (!captureResult || !captureResult.ok) {
          state.suggestStatus = captureResult
            ? (captureResult.reason || "Could not read the current graph.")
            : "Could not read the current graph.";
        } else {
          state.graphJson = captureResult.graphJson;
          state.graphCaptured = true;
          state.suggestedTargets = suggestAllBindings(captureResult.graphJson);
          const found = Object.values(state.suggestedTargets).filter((t) => t && t.length).length;
          state.suggestStatus = found
            ? `Found likely targets for ${found} binding${found === 1 ? "" : "s"}. Confirm each one below.`
            : "No likely targets found in the current graph. Bind each row manually.";
        }
      } catch (err) {
        state.suggestStatus = (err && err.message) || "Could not read the current graph.";
      }
      suggestBtn.disabled = false;
      renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
    },
  });
  suggestWrap.appendChild(suggestBtn);
  if (state.suggestStatus) {
    suggestWrap.appendChild(el("p", {
      "data-testid": "wizard-suggest-status",
      style: "font-size:10px;color:#888;margin:4px 0 0;",
      text: state.suggestStatus,
    }));
  }
  body.appendChild(suggestWrap);

  const reqHeading = el("h4", {
    style: "font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;margin:12px 0 4px;",
    text: "Required Bindings",
  });
  body.appendChild(reqHeading);

  const requiredList = renderBindingRowList(requiredDefs, state, graphContext, "wizard-required-bindings");
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

    const optionalList = renderBindingRowList(optionalDefs, state, graphContext, "wizard-optional-bindings");
    body.appendChild(optionalList);
  }

  // ── Binding summary (T2I save gate) ─────────────────────────────────
  // Save stays blocked until every required role holds a valid concrete
  // binding (exact node widget/field). Non-catalog bindings never count.
  const requiredKeys = collectRequiredBindings(state.selectedFeatures).map((b) => b.key);
  const boundCount = requiredKeys.filter((k) => isValidConcreteBinding(state.bindings[k])).length;
  const summary = el("p", {
    "data-testid": "wizard-save-gate",
    style: "font-size:11px;color:#888;margin-top:8px;",
    text: `${boundCount} of ${requiredKeys.length} required bindings complete • API graph ${graphOk ? "ready" : "unavailable"}`,
  });
  body.appendChild(summary);
}

// ── Step: Dependencies (version-setup mode) ─────────────────────────────
//
// Validation aid ordered before Bindings.  Reuses the exact dependency
// report shape + renderer from the workflow detail page.  Nothing here
// auto-downloads, auto-installs, or auto-reboots: each missing model row
// offers explicit "Queue install" (async) / "Install now" (sync), and each
// missing pack row offers a single Manager-backed "Install now".

function _missingModels(deps) {
  const models = deps && Array.isArray(deps.models) ? deps.models : [];
  return models.filter((m) => m && m.state !== "installed");
}

/** Basename for path-like names ("a/b/c.safetensors" → "c.safetensors"). */
function _basename(name) {
  const value = String(name || "");
  const idx = Math.max(value.lastIndexOf("/"), value.lastIndexOf("\\"));
  return idx === -1 ? value : value.slice(idx + 1);
}

/**
 * Manager catalog record for a missing model: exact filename first, then the
 * catalog basename, with role/type compatibility. Mirrors the row renderer's
 * resolution so `Download all` agrees with the per-row actions.
 */
function _managerModelFor(m, managerModelsByFilename) {
  return matchManagerModel(m, managerModelsByFilename);
}

/** Effective download URL: report source first, then Manager catalog. */
function _modelDownloadUrl(m, managerModelsByFilename) {
  const src = Array.isArray(m.source_urls) && m.source_urls[0];
  if (src) return src;
  const managed = _managerModelFor(m, managerModelsByFilename);
  return (managed && managed.url) || "";
}

/**
 * Effective save path: report folder first, then Manager catalog. A catalog
 * `save_path` of "default" is normalized through Manager's type→folder map.
 */
function _modelSavePath(m, managerModelsByFilename) {
  if (m.folder) return m.folder;
  const managed = _managerModelFor(m, managerModelsByFilename);
  if (managed) {
    const normalized = normalizeManagerSavePath(managed.savePath, managed.type);
    if (normalized) return normalized;
  }
  return _roleToFolder(m.role);
}

function _missingModelsWithUrl(deps, managerModelsByFilename) {
  return _missingModels(deps).filter((m) => _modelDownloadUrl(m, managerModelsByFilename));
}

function _missingModelsWithoutUrl(deps, managerModelsByFilename) {
  return _missingModels(deps).filter((m) => !_modelDownloadUrl(m, managerModelsByFilename));
}

/** Best-effort folder bucket when the dependency report omits one. */
function _roleToFolder(role) {
  const r = String(role || "").toLowerCase();
  if (r.includes("vae")) return "vae";
  if (r.includes("clip") || r.includes("text_encoder")) return "clip";
  if (r.includes("lora")) return "loras";
  if (r.includes("unet") || r.includes("diffusion")) return "unet";
  if (r.includes("controlnet")) return "controlnet";
  if (r.includes("upscal")) return "upscale_models";
  return "checkpoints";
}

function _rerenderWizard(state) {
  const panel = _wizardRoot && _wizardRoot.querySelector(".comfymodal-studio-wizard-panel");
  if (panel) renderWizard(panel, state);
}

function renderDependenciesStep(body, state) {
  if (!state.isVersionSetup) {
    body.appendChild(el("p", {
      class: "comfymodal-studio-wizard-description",
      "data-testid": "wizard-dependencies-unavailable",
      text: "Dependency validation is available for workflow versions.",
    }));
    return;
  }

  if (!state.dependencies) {
    body.appendChild(el("p", {
      class: "comfymodal-studio-wizard-description",
      "data-testid": "wizard-dependencies-loading",
      text: "Loading dependency report…",
    }));
    return;
  }

  const managerModels = state.managerModelsByFilename || null;
  const missingWithUrl = _missingModelsWithUrl(state.dependencies, managerModels);
  const missingNoUrl = _missingModelsWithoutUrl(state.dependencies, managerModels);

  body.appendChild(el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0 0 8px;" }, [
    el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "wizard-download-all",
      text: state.dependenciesBusy ? "Downloading…" : `Download all (${missingWithUrl.length})`,
      disabled: state.dependenciesBusy || missingWithUrl.length === 0,
      style: "width:auto;padding:4px 10px;font-size:11px;",
      onclick: () => downloadMissingModels(state),
    }),
    el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "wizard-dependencies-refresh",
      text: "Refresh",
      disabled: state.dependenciesBusy,
      style: "width:auto;padding:4px 10px;font-size:11px;",
      onclick: () => prefetchVersionDependencies(state),
    }),
  ]));

  if (missingNoUrl.length > 0) {
    body.appendChild(el("p", {
      "data-testid": "wizard-download-skipped",
      style: "font-size:10px;color:#888;margin:0 0 8px;",
      text: `${missingNoUrl.length} missing model${missingNoUrl.length === 1 ? "" : "s"} have no source URL and will be skipped by Download all.`,
    }));
  }

  const managerRow = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0 0 8px;" });
  managerRow.appendChild(el("span", {
    "data-testid": "wizard-manager-status",
    style: "font-size:10px;color:#888;",
    text: !state.managerProbed
      ? "Checking for ComfyUI-Manager…"
      : state.managerDetected
        ? "ComfyUI-Manager detected."
        : "Manager not detected — pack installs fall back to approval requests.",
  }));
  if (state.managerDetected && state.restartRequired) {
    managerRow.appendChild(el("span", {
      "data-testid": "wizard-restart-required",
      style: "font-size:10px;color:#fbbf24;",
      text: state.rebootInFlight ? "Rebooting — waiting for reconnect…" : "Restart required.",
    }));
    managerRow.appendChild(el("button", {
      class: "comfymodal-secondary-btn",
      "data-testid": "wizard-manager-reboot",
      text: state.rebootInFlight ? "Waiting…" : "Reboot ComfyUI",
      disabled: state.rebootInFlight,
      "aria-busy": state.rebootInFlight ? "true" : "false",
      style: "width:auto;padding:2px 8px;font-size:10px;",
      onclick: () => rebootManagerAndReport(state),
    }));
  }
  body.appendChild(managerRow);

  if (state.dependenciesMessage) {
    body.appendChild(el("p", {
      "data-testid": "wizard-dependencies-message",
      style: "font-size:10px;color:#aaa;margin:0 0 8px;",
      text: state.dependenciesMessage,
    }));
  }

  // Full report: reuse the detail page's renderer so markup/testids stay
  // identical (dependency-status, dependency-model-row, dependency-node-row).
  const depSection = renderDependencySection(null, state.dependencies, null, {
    apiBase: state._apiBase,
    managerInstalled: state.managerInstalled || [],
    installingPack: state.installingPack,
    onInstallPack: (n, plan) => installPackViaManager(state, n, plan),
    managerModelsByFilename: state.managerModelsByFilename || null,
    managerPacks: state.managerPacks || null,
    onDepsRefresh: () => prefetchVersionDependencies(state),
    // Once an install settles the report is the truth: drop the pseudo-status
    // and re-render so the badge shows Installed/Missing, never a stale queue.
    onInstallSettled: (m) => {
      _clearModelInstall(state, m);
      _rerenderWizard(state);
    },
  });
  body.appendChild(depSection);

  // Re-apply wizard-tracked in-flight status beside the rows and observe the
  // shared row's own error notes so a failed install clears its status too.
  _wireInstallStatus(depSection, state);

  _maybeProbeManager(state);
}

// ── In-flight install status (models + custom nodes) ─────────────────────
//
// The row's OWN state badge is the single source of truth for install state,
// so the wizard tracks status in state and re-applies it to that same badge
// after every render (never a detached supplemental chip). A wizard re-render
// (Manager probe finishing, dependency refresh) rebuilds rows from the report
// state, so without this the queued/downloading state would be lost. Never
// auto-installs; reads explicit clicks only.

const MODEL_QUEUED_STATUS = "Queued for download";
const DOWNLOADING_STATUS = "Downloading\u2026";

function _modelStatusKey(m) {
  if (!m) return "";
  return String(m.key || m.filename || "");
}

function _modelRowKey(row) {
  if (!row) return "";
  const own = row.getAttribute && row.getAttribute("data-model-key");
  if (own) return own;
  const holder = row.querySelector && row.querySelector("[data-model-key]");
  return holder ? holder.getAttribute("data-model-key") || "" : "";
}

/** "Downloading…" is the only status that is not a queued pseudo-state. */
function _statusKind(status) {
  return /downloading/i.test(status || "") ? "downloading" : "queued";
}

function _setBadge(row, testid, status) {
  if (!row || !status) return;
  const badge = row.querySelector && row.querySelector('[data-testid="' + testid + '"]');
  applyDependencyInflightBadge(badge, _statusKind(status), status);
}

function _applyInFlightStatus(section, state) {
  if (!section || !state) return;
  section.querySelectorAll('[data-testid="dependency-model-row"]').forEach((row) => {
    const key = _modelRowKey(row);
    _setBadge(row, "dependency-model-state", key ? state.modelInstalls[key] : "");
  });
  section.querySelectorAll('[data-testid="dependency-node-row"]').forEach((row) => {
    const name = (row.getAttribute && row.getAttribute("data-node-name")) || "";
    _setBadge(row, "dependency-node-state", name ? state.nodeInstalls[name] : "");
  });
}

/** A failed row install restores the badge to the report's real state. */
function _restoreRowBadge(row, key, name, state) {
  if (!row) return;
  const badge = row.querySelector
    && row.querySelector('[data-testid="dependency-model-state"], [data-testid="dependency-node-state"]');
  if (!badge) return;
  const deps = (state && state.dependencies) || {};
  let reportState = "missing";
  if (key) {
    const m = (Array.isArray(deps.models) ? deps.models : []).find((x) => _modelStatusKey(x) === key);
    if (m && m.state) reportState = m.state;
  }
  if (name) {
    const n = (Array.isArray(deps.custom_nodes) ? deps.custom_nodes : []).find((x) => x && String(x.name) === name);
    if (n && n.state) reportState = n.state;
  }
  applyDependencyStateBadge(badge, reportState);
}

/** Drop a settled model's tracked status so the report's truth wins. */
function _clearModelInstall(state, m) {
  const key = _modelStatusKey(m);
  if (key && state.modelInstalls[key]) delete state.modelInstalls[key];
}

/** Clear statuses whose item is now installed (or gone from the report). */
function _reconcileInstallStatus(state) {
  if (!state || !state.dependencies) return;
  const models = Array.isArray(state.dependencies.models) ? state.dependencies.models : [];
  const nodeRows = Array.isArray(state.dependencies.custom_nodes) ? state.dependencies.custom_nodes : [];
  const presentModels = new Set();
  models.forEach((m) => {
    const key = _modelStatusKey(m);
    if (!key) return;
    presentModels.add(key);
    if (m.state === "installed") delete state.modelInstalls[key];
  });
  Object.keys(state.modelInstalls).forEach((key) => {
    if (!presentModels.has(key)) delete state.modelInstalls[key];
  });
  const presentNodes = new Set();
  nodeRows.forEach((n) => {
    const name = n && n.name ? String(n.name) : "";
    if (!name) return;
    presentNodes.add(name);
    if (n.state === "installed") delete state.nodeInstalls[name];
  });
  Object.keys(state.nodeInstalls).forEach((name) => {
    if (!presentNodes.has(name)) delete state.nodeInstalls[name];
  });
}

function _wireInstallStatus(section, state) {
  if (!section || !state) return;
  _applyInFlightStatus(section, state);
  // Explicit click marks the item in wizard state before the shared row's own
  // handler runs; a re-render then keeps the badge visible.
  section.addEventListener("click", (ev) => {
    const target = ev.target;
    if (!target || typeof target.closest !== "function") return;
    const modelBtn = target.closest(
      '[data-testid="dependency-model-queue"], [data-testid="dependency-model-install-now"], [data-testid="dependency-model-url-install"]'
    );
    if (modelBtn) {
      const key = modelBtn.getAttribute("data-model-key") || _modelRowKey(modelBtn.closest('[data-testid="dependency-model-row"]'));
      if (!key) return;
      // Queue/bulk installs read "Queued for download"; synchronous installs
      // read "Downloading…". Both update the SAME row state badge.
      const id = modelBtn.getAttribute("data-testid");
      state.modelInstalls[key] = id === "dependency-model-queue" ? MODEL_QUEUED_STATUS : DOWNLOADING_STATUS;
      _applyInFlightStatus(section, state);
      return;
    }
    const nodeBtn = target.closest('[data-testid="dependency-node-install-now"]');
    if (nodeBtn) {
      const name = nodeBtn.getAttribute("data-node-name") || "";
      if (!name) return;
      state.nodeInstalls[name] = "Queued";
      _applyInFlightStatus(section, state);
    }
  }, true);
  // Each render rebuilds the section; drop the previous observer so repeated
  // re-renders cannot accumulate watchers on detached rows.
  if (state._installStatusObserver) {
    try { state._installStatusObserver.disconnect(); } catch (e) { /* already gone */ }
  }
  state._installStatusObserver = _watchInstallFailures(section, state);
}

/** A failed row install (note gains `error`) restores its report state. */
function _watchInstallFailures(section, state) {
  if (!section || typeof MutationObserver === "undefined") return null;
  try {
    const observer = new MutationObserver((records) => {
      records.forEach((rec) => {
        const note = rec.target;
        if (!note || !note.classList || !note.classList.contains("error")) return;
        const row = note.closest
          ? note.closest('[data-testid="dependency-model-row"], [data-testid="dependency-node-row"]')
          : null;
        if (!row) return;
        const key = _modelRowKey(row);
        const name = (row.getAttribute && row.getAttribute("data-node-name")) || "";
        if (key && state.modelInstalls[key]) delete state.modelInstalls[key];
        if (name && state.nodeInstalls[name]) delete state.nodeInstalls[name];
        _restoreRowBadge(row, key, name, state);
      });
    });
    observer.observe(section, { subtree: true, attributes: true, attributeFilter: ["class"] });
    return observer;
  } catch (e) { /* observation is best-effort */ }
  return null;
}

async function prefetchVersionDependencies(state) {
  if (!state || !state.isVersionSetup) return;
  try {
    const resp = await getVersionDependencies(state._apiBase, state.workflowVersionId);
    if (_wizardState !== state) return;
    state.dependencies = resp && resp.status === "ok" ? resp : null;
    // The fresh report is the truth: installed items drop their in-flight
    // status. The current step is preserved — Refresh never leaves the wizard.
    _reconcileInstallStatus(state);
    _rerenderWizard(state);
  } catch (e) { /* best-effort; the step simply stays hidden */ }
}

async function downloadMissingModels(state) {
  if (!state || state.dependenciesBusy) return;
  const managerModels = state.managerModelsByFilename || null;
  const models = _missingModelsWithUrl(state.dependencies, managerModels);
  if (models.length === 0) {
    state.dependenciesMessage = "No missing models with a source URL to download.";
    _rerenderWizard(state);
    return;
  }
  const items = models.map((m) => ({
    url: _modelDownloadUrl(m, managerModels),
    filename: m.filename || "",
    save_path: _modelSavePath(m, managerModels),
  }));
  const skipped = _missingModelsWithoutUrl(state.dependencies, managerModels).length;
  state.dependenciesBusy = true;
  // Beside each row: bulk downloads are tracked per model key too, so a
  // re-render during the batch keeps the queued state on the row's badge.
  models.forEach((m) => {
    const key = _modelStatusKey(m);
    if (key) state.modelInstalls[key] = MODEL_QUEUED_STATUS;
  });
  state.dependenciesMessage = `Requesting ${items.length} model download${items.length === 1 ? "" : "s"}…`;
  _rerenderWizard(state);
  const resp = await batchInstallModels(state._apiBase, items);
  if (_wizardState !== state) return;
  state.dependenciesBusy = false;
  if (!resp || resp.status !== "ok") {
    models.forEach((m) => {
      const key = _modelStatusKey(m);
      if (key) delete state.modelInstalls[key];
    });
    state.dependenciesMessage = "Download all failed: "
      + ((resp && (resp.message || resp.error)) || "request failed");
    _rerenderWizard(state);
    return;
  }
  let message = `Requested ${items.length} model download${items.length === 1 ? "" : "s"}.`;
  if (skipped > 0) message += ` Skipped ${skipped} without a source URL.`;
  await rescanModels(state._apiBase);
  if (_wizardState !== state) return;
  await prefetchVersionDependencies(state);
  if (_wizardState !== state) return;
  // The batch settled: the refreshed report is truth, so drop the queued
  // pseudo-status before the final render.
  models.forEach((m) => {
    const key = _modelStatusKey(m);
    if (key) delete state.modelInstalls[key];
  });
  state.dependenciesMessage = message;
  _rerenderWizard(state);
}

/**
 * Parse Manager's `/customnode/installed` response. It is a dict keyed by
 * module name with `{ ver, cnr_id, aux_id, enabled }` values (NOT a
 * `{ nodes: [...] }` envelope). Preserve `enabled=false` truthfully so a
 * disabled pack is not reported as ready.
 */
async function _refreshManagerInstalled(state) {
  const installed = await listManagerInstalled();
  if (_wizardState !== state) return;
  const records = [];
  if (installed && installed.ok) {
    const data = installed.data;
    if (data && typeof data === "object" && !Array.isArray(data)) {
      Object.keys(data).forEach((module) => {
        const info = data[module];
        if (!info || typeof info !== "object" || Array.isArray(info)) return;
        records.push({
          module: module,
          ver: info.ver || "",
          cnr_id: info.cnr_id || "",
          aux_id: info.aux_id || "",
          enabled: !(info.enabled === false || String(info.enabled).toLowerCase() === "false"),
        });
      });
    } else if (Array.isArray(data)) {
      // Defensive: tolerate a list shape without inventing fields.
      data.forEach((info) => {
        if (info && typeof info === "object") records.push(info);
      });
    }
  }
  state.managerInstalled = records;
}

function _maybeProbeManager(state) {
  if (!state || state.managerProbed || state.managerProbing) return;
  state.managerProbing = true;
  (async () => {
    const version = await getManagerVersion();
    if (_wizardState !== state) return;
    state.managerDetected = !!(version && version.ok);
    if (state.managerDetected) await _refreshManagerInstalled(state);
    if (state.managerDetected) await _loadManagerModels(state);
    if (state.managerDetected) await _loadManagerPacks(state);
    if (_wizardState !== state) return;
    state.managerProbing = false;
    state.managerProbed = true;
    _rerenderWizard(state);
  })();
}

/**
 * Load the Manager model catalog once per wizard. Records are keyed by
 * filename and by basename (Manager catalogs basenames); a `save_path` of
 * "default" is normalized through Manager's type→folder map so an install
 * lands in a real folder.
 */
async function _loadManagerModels(state) {
  try {
    const models = await getManagerModels();
    if (!state || _wizardState !== state) return;
    const map = {};
    (models || []).forEach((m) => {
      if (!m || !m.filename) return;
      const record = {
        url: m.url || "",
        reference: m.reference || "",
        savePath: normalizeManagerSavePath(m.save_path, m.type),
        type: m.type || "",
        name: m.name || "",
        installed: m.installed,
      };
      if (!map[m.filename]) map[m.filename] = record;
      const base = _basename(m.filename);
      if (base && base !== m.filename && !map[base]) map[base] = record;
    });
    state.managerModelsByFilename = map;
  } catch (e) { /* catalog is best-effort */ }
}

/**
 * Load Manager's pack list + class mappings once per wizard and build the
 * class/CNR-id → pack index used to resolve missing custom-node rows to a
 * pack repository. Best-effort: an absent/empty catalog leaves the index
 * null, so rows simply keep their report-supplied repository (if any).
 */
async function _loadManagerPacks(state) {
  try {
    const [packList, mappings] = await Promise.all([
      getManagerPackList(),
      getManagerMappings(),
    ]);
    if (!state || _wizardState !== state) return;
    state.managerPacks = buildManagerPackIndex(packList, mappings);
  } catch (e) { /* catalog is best-effort */ }
}

async function installPackViaManager(state, node, installPlan) {
  if (!state || state.installingPack) return;
  const plan = installPlan || { kind: "none" };
  const src = node || {};
  const label = src.name || plan.name || src.cnr_id || src.aux_id
    || src.repository_url || "pack";
  state.installingPack = label;
  state.nodeInstalls[label] = "Queued";
  state.dependenciesMessage = `Installing ${label}…`;
  _rerenderWizard(state);
  const res = await performManagerInstall(plan);
  if (_wizardState !== state) return;
  state.installingPack = null;
  delete state.nodeInstalls[label];
  if (!res.ok) {
    state.dependenciesMessage = res.message;
    _rerenderWizard(state);
    return;
  }
  // Explicit install succeeded. Python custom nodes normally need a ComfyUI
  // restart to import, so restartRequired stays truthful. Best-effort refresh
  // the canonical registry and re-resolve the version: only the dependency
  // resolver can report the classes actually installed, so the row is never
  // claimed installed from the Manager package/queue alone. Never reboots.
  state.restartRequired = true;
  try { await refreshCustomNodes(state._apiBase); } catch (e) { /* best-effort */ }
  if (_wizardState !== state) return;
  await _refreshManagerInstalled(state);
  if (_wizardState !== state) return;
  await prefetchVersionDependencies(state);
  if (_wizardState !== state) return;
  // Only the dependency resolver can confirm the classes loaded; when the
  // report is unavailable or still missing, say so rather than implying the
  // install is complete.
  const classesConfirmed =
    !!state.dependencies && _unresolvedNodeClasses(state.dependencies).length === 0;
  state.dependenciesMessage = classesConfirmed
    ? res.message
    : `${res.message} Package present, but required classes are not loaded.`;
  _rerenderWizard(state);
}

/** Custom-node dependency rows the resolver still does not report installed. */
function _unresolvedNodeClasses(deps) {
  const nodes = deps && Array.isArray(deps.custom_nodes) ? deps.custom_nodes : [];
  return nodes.filter((n) => n && n.state !== "installed");
}

async function rebootManagerAndReport(state) {
  if (!state || state.rebootInFlight) return;
  state.rebootInFlight = true;
  state.dependenciesMessage = "Rebooting ComfyUI — waiting for it to reconnect…";
  _rerenderWizard(state);
  // The reboot POST is expected to drop the connection; success is decided by
  // the bounded reconnect probes, never by the POST response. Explicit click
  // only — nothing here ever reboots on its own.
  const res = await managerRebootAndWait({
    expectManager: state.managerDetected === true,
    onPhase: (phase) => {
      if (_wizardState !== state) return;
      state.dependenciesMessage = phase === "manager"
        ? "ComfyUI reconnected — waiting for ComfyUI-Manager…"
        : "Rebooting ComfyUI — waiting for it to reconnect…";
      _rerenderWizard(state);
    },
  });
  if (_wizardState !== state) return;
  state.rebootInFlight = false;
  if (res && res.ok) {
    state.restartRequired = false;
    state.dependenciesMessage = "ComfyUI rebooted and reconnected.";
    // Re-probe Manager and re-resolve dependencies against the fresh runtime;
    // the wizard stays open on the same step throughout.
    state.managerProbed = false;
    state.managerProbing = false;
    await prefetchVersionDependencies(state);
  } else {
    state.dependenciesMessage = (res && res.message)
      || "ComfyUI did not reconnect after the reboot request — restart it manually if needed.";
  }
  _rerenderWizard(state);
}

// ── Binding row list renderer ────────────────────────────────────────────

function renderBindingRowList(bindingDefs, state, graphContext, listTestid) {
  const listProps = { class: "comfymodal-studio-wizard-binding-list" };
  if (listTestid) listProps["data-testid"] = listTestid;
  const list = el("div", listProps);
  const graphOk = (graphContext && graphContext.ok) || state.graphCaptured;

  bindingDefs.forEach((bindingDef) => {
    const bindingValue = state.bindings[bindingDef.key];
    const isBound = Boolean(bindingValue && bindingValue.nodeId);
    const isCaptureActive = state.bindingCaptureActive === bindingDef.key;

    // Labels come from the code-owned bindable-input catalog only.
    const defLabel = bindingDef.label || bindingDef.key;
    const defHelp = bindingDef.helpText || "";

    const row = el("div", {
      class: "comfymodal-studio-wizard-binding-row"
        + (isBound ? " bound" : "")
        + (isCaptureActive ? " capturing" : ""),
      "data-testid": "wizard-binding-row",
      "data-binding-key": bindingDef.key,
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
          // Mirror the canvas-click capture auto-select
          // (studio-graph-binding.js): an unambiguous single candidate is
          // the confirmed field. Without this a single-candidate manual
          // capture stores a field-less node-only binding with no dropdown
          // to fix it, and the save gate can never advance for that row.
          const selectedCandidates = selected.candidates || [];
          let selWidgetName = selected.widgetName;
          let selInputName = selected.inputName;
          let selOutputIndex = selected.outputIndex;
          if (selectedCandidates.length === 1) {
            const c = selectedCandidates[0];
            if (c.kind === "widget") selWidgetName = c.name;
            else if (c.kind === "input") selInputName = c.name;
            else if (c.kind === "output") selOutputIndex = c.index;
          }
          // Phase 4: extract widgetSchema from the selected candidate
          const selCandidate = _findSelectedCandidate(
            selected.candidates,
            { widgetName: selected.widgetName, inputName: selected.inputName, outputIndex: selected.outputIndex }
          );
          const selWidgetSchema = _buildWidgetSchemaFromCandidate(selCandidate);
          // Refuse captures with no confirmable field: a node-only binding
          // would look bound while the save gate can never count it. This
          // covers zero candidates AND the lone node-fallback candidate
          // (extractNodeCandidates emits kind "node" when a node exposes no
          // widgets/inputs/outputs) — neither yields a field, and the
          // dropdown cannot fix it (node options are not offered).
          const selHasField = selWidgetName || selInputName || selOutputIndex != null;
          const selPickable = selectedCandidates.some((c) => c && (c.kind === "widget" || c.kind === "input" || c.kind === "output"));
          if (!selHasField && !selPickable) {
            const nodeLabel = selected.nodeTitle || selected.nodeType || ("Node " + selected.nodeId);
            state.captureNotice = { key: bindingDef.key, message: nodeLabel + " exposes no bindable fields — pick a node with widgets or connections." };
            cancelGraphBinding();
            state.bindingCaptureActive = null;
            renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
            return;
          }
          if (state.captureNotice && state.captureNotice.key === bindingDef.key) state.captureNotice = null;
          state.bindings[bindingDef.key] = {
            kind: selWidgetName ? "widget" : selInputName ? "input" : selOutputIndex != null ? "output" : "node",
            nodeId: selected.nodeId,
            nodeType: selected.nodeType,
            nodeTitle: selected.nodeTitle,
            widgetName: selWidgetName,
            inputName: selInputName,
            outputIndex: selOutputIndex,
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

    // Bound rows: a View aid that centers + highlights the node on the
    // canvas.  Disabled (never hidden) when the node is not on the live
    // canvas, so the row layout stays stable.
    if (isBound) {
      row.appendChild(renderViewButton(bindingValue.nodeId, {
        testid: "wizard-view-binding",
        bindingKey: bindingDef.key,
        state,
      }));
    }

    // Unbound rows: show the likely-target hint, plus a one-click
    // confirmation when the graph scan found a concrete target. The click
    // below IS the required exact-target confirmation — suggestions are
    // never applied without it.
    if (!isBound && !isCaptureActive) {
      const scanned = (state.suggestedTargets && state.suggestedTargets[bindingDef.key]) || [];
      if (scanned.length > 0) {
        const first = scanned[0];
        const targetLabel = first.widgetName
          ? `widget: ${first.widgetName}`
          : first.inputName
            ? `input: ${first.inputName}`
            : first.outputIndex != null
              ? `output #${first.outputIndex}`
              : "node";
        row.appendChild(el("div", { style: "margin-top:4px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;" }, [
          el("span", {
            style: "font-size:10px;color:#888;",
            text: `Suggested: ${first.nodeTitle || first.nodeType} → ${targetLabel}`,
          }),
          el("button", {
            class: "comfymodal-secondary-btn",
            "data-testid": "wizard-use-suggestion",
            "data-binding-key": bindingDef.key,
            text: "Use suggestion",
            style: "width:auto;padding:2px 8px;font-size:10px;",
            onclick: (event) => {
              event.preventDefault();
              event.stopPropagation();
              applySuggestedBinding(state, bindingDef.key, first);
              renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
            },
          }),
          renderViewButton(first.nodeId, {
            testid: "wizard-view-suggestion",
            bindingKey: bindingDef.key,
            state,
          }),
        ]));
      } else {
        const hint = _likelyTargetHint(bindingDef.key);
        if (hint) {
          row.appendChild(el("div", { style: "margin-top:4px;" }, [
            el("span", { style: "font-size:10px;color:#555;font-style:italic;", text: hint }),
          ]));
        }
        // Live-canvas fallback: the stored-graph scan found nothing (often
        // custom node types), but a matching node may sit on the canvas.
        // Each found target gets the same explicit Use + View confirmation
        // as scanned suggestions — nothing is ever auto-bound.
        const found = findCanvasNodeTargets(ROLE_SUGGESTIONS[bindingDef.key], 3);
        found.forEach((target) => {
          const targetLabel = target.widgetName
            ? `widget: ${target.widgetName}`
            : target.inputName
              ? `input: ${target.inputName}`
              : target.outputIndex != null
                ? `output #${target.outputIndex}`
                : "node";
          row.appendChild(el("div", { style: "margin-top:4px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;" }, [
            el("span", {
              style: "font-size:10px;color:#888;",
              text: `Found: ${target.nodeTitle || target.nodeType} → ${targetLabel}`,
            }),
            el("button", {
              class: "comfymodal-secondary-btn",
              "data-testid": "wizard-use-found",
              "data-binding-key": bindingDef.key,
              text: "Use found",
              style: "width:auto;padding:2px 8px;font-size:10px;",
              onclick: (event) => {
                event.preventDefault();
                event.stopPropagation();
                applySuggestedBinding(state, bindingDef.key, target);
                renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
              },
            }),
            renderViewButton(target.nodeId, {
              testid: "wizard-view-found",
              bindingKey: bindingDef.key,
              state,
            }),
          ]));
        });
        if (found.length === 0) {
          // No live target: both buttons still render so every Likely row
          // offers the same actions; disabled with the reason until a
          // matching node is on the canvas.
          row.appendChild(el("div", { style: "margin-top:4px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;" }, [
            el("button", {
              class: "comfymodal-secondary-btn",
              "data-testid": "wizard-use-found",
              "data-binding-key": bindingDef.key,
              text: "Use found",
              disabled: true,
              title: "No matching node on the canvas — load the workflow or capture manually",
              style: "width:auto;padding:2px 8px;font-size:10px;",
            }),
            renderViewButton(null, {
              testid: "wizard-view-found",
              bindingKey: bindingDef.key,
              state,
            }),
          ]));
        }
      }
    }

    // Unbindable-capture notice: the picked node exposed no confirmable
    // field, so nothing was stored. This keeps the row honestly unbound
    // instead of a field-less pseudo-binding the save gate could never count.
    if (state.captureNotice && state.captureNotice.key === bindingDef.key) {
      row.appendChild(el("div", { style: "margin-top:4px;" }, [
        el("span", { style: "font-size:10px;color:#fbbf24;", text: state.captureNotice.message }),
      ]));
    }
    // View-failure notice: the node could not be centered/highlighted
    // (usually gone from the canvas after the row rendered).
    if (state.viewNotice && state.viewNotice.key === bindingDef.key) {
      row.appendChild(el("div", { style: "margin-top:4px;" }, [
        el("span", { style: "font-size:10px;color:#f87171;", text: state.viewNotice.message }),
      ]));
    }

    list.appendChild(row);
  });

  return list;
}

/**
 * "View" aid: centers + highlights a node on the ComfyUI canvas.
 * Null-safe — disabled when the node is not present on the live canvas.
 */
function renderViewButton(nodeId, opts) {
  const o = opts || {};
  const available = isGraphNodeAvailable(nodeId);
  return el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": o.testid || "wizard-view-node",
    "data-binding-key": o.bindingKey || "",
    "data-node-id": nodeId != null ? String(nodeId) : "",
    text: "View",
    title: available ? "Center this node on the canvas" : "Node is not on the current canvas",
    disabled: !available,
    style: "width:auto;padding:2px 8px;font-size:10px;align-self:flex-start;",
    onclick: (event) => {
      event.preventDefault();
      event.stopPropagation();
      let res = null;
      try { res = viewGraphNode(nodeId); } catch (e) { res = { ok: false }; }
      // Surface failures on the row: a silent no-op looks identical to a
      // working highlight otherwise (e.g. the node left the canvas between
      // render and click).
      if (!o.state) return;
      if (res && res.ok === false) {
        o.state.viewNotice = {
          key: o.bindingKey,
          message: res.reason || "Node is not on the current canvas",
        };
        const panel = _wizardRoot && _wizardRoot.querySelector(".comfymodal-studio-wizard-panel");
        if (panel) renderWizard(panel, o.state);
        setTimeout(() => {
          if (o.state.viewNotice && o.state.viewNotice.key === o.bindingKey) {
            o.state.viewNotice = null;
            const p = _wizardRoot && _wizardRoot.querySelector(".comfymodal-studio-wizard-panel");
            if (p) renderWizard(p, o.state);
          }
        }, 3500);
      } else if (o.state.viewNotice && o.state.viewNotice.key === o.bindingKey) {
        o.state.viewNotice = null;
      }
    },
  });
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
  const hasField = !!(currentWidget || currentInput || currentOutput != null);

  // No field stored yet (fresh manual capture): force an explicit pick so
  // the displayed first candidate is never mistaken for the stored binding.
  // Without this, activating the already-displayed option fires no change
  // event — nothing is written, nothing re-renders, and the save gate stays
  // shut with no way to confirm the shown field.
  if (!hasField) {
    const placeholder = el("option", { value: "", text: "Select field…" });
    placeholder.selected = true;
    select.appendChild(placeholder);
  }

  // Node-fallback candidates are never pickable (the change handler has no
  // field to store for them), so they are not offered as options.
  const pickableCandidates = (bindingValue.candidates || []).filter(
    (c) => c && (c.kind === "widget" || c.kind === "input" || c.kind === "output")
  );
  pickableCandidates.forEach((c) => {
    let isCurrent = false;
    if (c.kind === "widget") isCurrent = c.name === currentWidget;
    else if (c.kind === "input") isCurrent = c.name === currentInput;
    else if (c.kind === "output") isCurrent = c.index === currentOutput;

    const opt = el("option", {
      value: JSON.stringify({ kind: c.kind, name: c.name, index: c.index }),
      text: `${c.kind}: ${c.label}`,
    });
    if (isCurrent) opt.selected = true;
    select.appendChild(opt);
  });

  select.addEventListener("change", () => {
    if (!select.value) return; // placeholder re-selected: nothing to store
    let parsed = null;
    try {
      parsed = JSON.parse(select.value);
    } catch { /* ignore parse errors */ }
    if (!parsed) return;
    if (parsed.kind === "widget") {
      bindingValue.kind = "widget";
      bindingValue.widgetName = parsed.name;
      bindingValue.inputName = null;
      bindingValue.outputIndex = null;
    } else if (parsed.kind === "input") {
      bindingValue.kind = "input";
      bindingValue.inputName = parsed.name;
      bindingValue.widgetName = null;
      bindingValue.outputIndex = null;
    } else if (parsed.kind === "output") {
      bindingValue.kind = "output";
      bindingValue.outputIndex = parsed.index;
      bindingValue.widgetName = null;
      bindingValue.inputName = null;
    } else {
      return; // node-fallback or unknown kind: no field to store
    }
    // Phase 4: keep widgetSchema in sync with the selected candidate
    const updatedCandidate = _findSelectedCandidate(
      bindingValue.candidates,
      { widgetName: bindingValue.widgetName, inputName: bindingValue.inputName, outputIndex: bindingValue.outputIndex }
    );
    bindingValue.widgetSchema = _buildWidgetSchemaFromCandidate(updatedCandidate);
    renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
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
  if (state.captureNotice && state.captureNotice.key === bindingDef.key) state.captureNotice = null;
  if (state.viewNotice && state.viewNotice.key === bindingDef.key) state.viewNotice = null;
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
      // Same refusal as "Use Selected Node": no confirmable field (zero
      // candidates or only the node-fallback candidate) must not become a
      // pseudo-binding the gate can never count.
      const resHasField = result.widgetName || result.inputName || result.outputIndex != null;
      const resCandidates = result.candidates || [];
      const resPickable = resCandidates.some((c) => c && (c.kind === "widget" || c.kind === "input" || c.kind === "output"));
      if (!resHasField && !resPickable) {
        const nodeLabel = result.nodeTitle || result.nodeType || ("Node " + result.nodeId);
        state.captureNotice = { key: result.bindingKey, message: nodeLabel + " exposes no bindable fields — pick a node with widgets or connections." };
        state.bindingCaptureActive = null;
        renderWizard(_wizardRoot.querySelector(".comfymodal-studio-wizard-panel"), state);
        return;
      }
      if (state.captureNotice && state.captureNotice.key === result.bindingKey) state.captureNotice = null;
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
  // Version-setup mode: the mapping it saves carries no name or
  // description, so this step is the explicit confirmation — a read-only
  // summary plus the Save button in the footer. No Preset concepts appear.
  if (state.isVersionSetup) {
    const heading = el("h4", { class: "comfymodal-studio-wizard-section-title", text: "Confirm Setup" });
    body.appendChild(heading);

    const desc = el("p", {
      class: "comfymodal-studio-wizard-description",
      text: "Review the confirmed bindings, then save to map this workflow version.",
    });
    body.appendChild(desc);

    const summary = el("div", { style: "margin-top:12px;padding:8px;background:#0a0a0a;border:1px solid #2a2a2a;border-radius:3px;" });
    summary.appendChild(el("p", { text: `Features: ${state.selectedFeatures.join(", ")}`, style: "font-size:11px;color:#888;margin:0 0 4px;" }));
    summary.appendChild(el("p", { text: `Bindings: ${Object.keys(state.bindings).length} configured`, style: "font-size:11px;color:#888;margin:0;" }));
    body.appendChild(summary);
    return;
  }

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
  // Version-setup mode: the save persisted a version mapping (never a
  // snapshot or preset), so report only that — truthfully, from the
  // mapping POST response.
  if (state.isVersionSetup) {
    const mappingId = state.mappingResult && state.mappingResult.mapping_id;
    const success = el("div", { style: "text-align:center;padding:16px;" }, [
      el("div", { text: "\u2713", style: "font-size:32px;color:#4ade80;" }),
      el("h4", { text: "Setup Complete", style: "margin:8px 0;color:#d0d0d0;" }),
      el("p", {
        text: "This workflow version is now mapped.",
        style: "font-size:12px;color:#888;margin:0 0 8px;",
      }),
    ]);
    if (mappingId) {
      success.appendChild(el("p", {
        text: `Mapping: ${mappingId}`,
        style: "font-size:11px;color:#888;margin:4px 0;",
      }));
    }
    body.appendChild(success);
    return;
  }

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
    // ── Workflow-version setup flow (leaf 1.2.1) ──────────────────────
    // Persists the confirmed catalog bindings as the version's initial
    // mapping through the existing mapping POST route. The T2I save gate
    // is re-checked here (never trust the button state alone); no
    // snapshot or preset is created.
    if (state.isVersionSetup) {
      if (!checkAllRequiredBindings(state)) {
        state.step = "error";
        state.errorMessage = "All required bindings must be confirmed before saving.";
        return;
      }
      const mappingPayload = buildVersionMappingPayload(state);
      if (!mappingPayload) {
        state.step = "error";
        state.errorMessage = "All required bindings must be confirmed before saving.";
        return;
      }
      const mappingResp = await createMapping(apiBase, state.workflowVersionId, mappingPayload);
      if (!mappingResp || mappingResp.status === "error" || !mappingResp.mapping) {
        state.step = "error";
        state.errorMessage = (mappingResp && (mappingResp.message || mappingResp.error))
          || "Server rejected mapping creation";
        return;
      }
      state.mappingResult = mappingResp.mapping;
      state.step = "saved";
      return;
    }

    // Build nodeBindings from wizard state. Catalog roles only, and only
    // valid concrete bindings (exact confirmed widget/input/output field):
    // non-catalog graph inputs and unconfirmed node-only picks never persist.
    const nodeBindings = {};
    Object.entries(state.bindings).forEach(([key, val]) => {
      if (key !== OUTPUT_BINDING.key && !BINDABLE_INPUTS[key]) return;
      if (!isValidConcreteBinding(val)) return;
      nodeBindings[key] = {
        kind: val.kind || "node",
        nodeId: val.nodeId,
        nodeType: val.nodeType || "",
        nodeTitle: val.nodeTitle || "",
      };
      if (val.widgetName) nodeBindings[key].widgetName = val.widgetName;
      if (val.inputName) nodeBindings[key].inputName = val.inputName;
      if (val.outputIndex != null) nodeBindings[key].outputIndex = val.outputIndex;
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

// ── Workflow-version setup helpers (leaf 1.2.1) ──────────────────────────

/**
 * Pre-seed suggestions from the bound version's stored graph so the
 * bindings step is usable without the live ComfyUI graph (e.g. a version
 * imported earlier). Best-effort: on any failure the wizard keeps working
 * through the live-graph "Suggest from current graph" button.
 */
async function prefetchVersionSetupGraph(state) {
  const apiBase = state._apiBase;
  const versionId = state.workflowVersionId;
  let version = null;
  try {
    const resp = await getWorkflowVersion(apiBase, versionId);
    if (resp && resp.version && resp.version.workflow_version_id) {
      version = resp.version;
    }
  } catch (e) {
    version = null;
  }
  if (!state || _wizardState !== state) return; // closed or replaced meanwhile
  const graph = version && (version.graph_json || version.graphJson);
  if (!graph) return;
  state.graphJson = graph;
  state.graphCaptured = true;
  try {
    state.suggestedTargets = suggestAllBindings(graph);
    const found = Object.values(state.suggestedTargets).filter((t) => t && t.length).length;
    if (found) {
      state.suggestStatus = `Found likely targets for ${found} binding${found === 1 ? "" : "s"} in this version's stored graph. Confirm each one below.`;
    }
  } catch (e) { /* suggestions are best-effort */ }
  const panel = _wizardRoot && _wizardRoot.querySelector(".comfymodal-studio-wizard-panel");
  if (panel) renderWizard(panel, state);
}

/** Catalog block → server mapping control_kind vocabulary. */
function _versionMappingControlKind(key) {
  const entry = BINDABLE_INPUTS[key];
  const block = entry && entry.block;
  if (block === "multiline") return "multiline";
  if (block === "integer") return "integer";
  if (block === "float") return "number";
  if (block === "model-picker") return "file";
  if (block === "boolean") return "boolean";
  return "string";
}

/**
 * Translate confirmed concrete catalog bindings into the version-mapping
 * POST shape: entries as a dict keyed by semantic role (the server-side
 * mapping contract) plus the output node id. Returns null when the T2I
 * save gate is not satisfied. Only valid concrete bindings (exact
 * confirmed widget/input/output field) persist — same rule as the preset
 * nodeBindings builder.
 */
function buildVersionMappingPayload(state) {
  const bindings = (state && state.bindings) || {};
  const outputBinding = bindings[OUTPUT_BINDING.key];
  if (!isValidConcreteBinding(outputBinding)) return null;
  const entries = {};
  Object.keys(bindings).forEach((key) => {
    if (key === OUTPUT_BINDING.key) return;
    if (!BINDABLE_INPUTS[key]) return;
    const val = bindings[key];
    if (!isValidConcreteBinding(val)) return;
    entries[key] = {
      semantic_role: key,
      node_id: String(val.nodeId),
      input_name: val.widgetName || val.inputName || "",
      output_name: "",
      kind: val.kind === "widget" ? "widget"
        : val.kind === "input" ? "node_input"
        : val.kind === "output" ? "node_output" : "node",
      data_type: "",
      control_kind: _versionMappingControlKind(key),
      display_name: (BINDABLE_INPUTS[key] && BINDABLE_INPUTS[key].name) || key,
      required: T2I_SAVE_GATE_KEYS.indexOf(key) !== -1,
    };
  });
  if (Object.keys(entries).length === 0) return null;
  return { entries: entries, output_node_id: String(outputBinding.nodeId) };
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
  (featureIds || []).forEach((fid) => {
    const def = _featureDef(fid);
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
  (featureIds || []).forEach((fid) => {
    const def = _featureDef(fid);
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

/**
 * T2I save gate: every required catalog role (+ output) must hold a valid
 * concrete binding. Bindings with a nodeId but no confirmed widget/input/
 * output field do NOT count, and non-catalog keys are ignored entirely.
 */
function checkAllRequiredBindings(state) {
  if (!state) return false;
  const required = collectRequiredBindings(state.selectedFeatures);
  return required.every((b) => isValidConcreteBinding(state.bindings && state.bindings[b.key]));
}

/**
 * Store a graph-scan suggestion as the role's binding. This is the explicit
 * user confirmation step: callers invoke it only from the "Use suggestion"
 * click (or an equivalent deliberate confirm), never automatically.
 */
function applySuggestedBinding(state, roleKey, suggestion) {
  if (!state || !roleKey || !suggestion || suggestion.nodeId == null) return false;
  if (!ROLE_SUGGESTIONS[roleKey]) return false; // catalog roles only
  if (state.captureNotice && state.captureNotice.key === roleKey) state.captureNotice = null;
  if (state.viewNotice && state.viewNotice.key === roleKey) state.viewNotice = null;
  state.bindings[roleKey] = {
    kind: suggestion.widgetName ? "widget" : suggestion.inputName ? "input" : suggestion.outputIndex != null ? "output" : "node",
    nodeId: suggestion.nodeId,
    nodeType: suggestion.nodeType || "",
    nodeTitle: suggestion.nodeTitle || "",
    widgetName: suggestion.widgetName || null,
    inputName: suggestion.inputName || null,
    outputIndex: suggestion.outputIndex != null ? suggestion.outputIndex : null,
    label: suggestion.nodeTitle || suggestion.nodeType || "",
    candidates: [],
    widgetSchema: null,
  };
  return true;
}

function closePresetWizardAndNotify() {
  const onDone = _wizardState ? _wizardState._onDone : null;
  closePresetWizard();
  if (onDone) onDone();
}

// ── Exported for test access ────────────────────────────────────────────
// (suggestBindingTargets, suggestAllBindings, and isValidConcreteBinding
// are exported inline at their definitions.)

export {
  FEATURE_DEFS,
  makeInitialState,
  collectRequiredBindings,
  checkAllRequiredBindings,
  applySuggestedBinding,
  T2I_SAVE_GATE_KEYS,
};
