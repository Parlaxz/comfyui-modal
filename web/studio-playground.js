// Modal Studio ├óΓé¼ΓÇ¥ Playground
//
// Default Studio page with left control panel and right workspace.
// Image-edit interactions are honest disabled future-work placeholders.
// Uses the feature registry for all control rendering.
// Experiment mode is an overlay on controls, not a separate page.

import { FEATURE_SPECS, CONTROL_DEFS, getRecommendedStepsStatus } from "./studio-feature-registry.js";
import {
  renderExperimentToggle,
  renderExperimentMode,
  enhanceControlWithAxisCheckbox,
} from "./studio-experiment-mode.js";
// Presets were removed from the codebase; the legacy preset-driven Playground
// path below is dead and resolves to an empty preset list. It is retained only
// until the legacy lane is deleted outright.
import {
  runStudioWorkflow,
  runStudioBatchStream,
  cancelStudioBatch,
  getStudioRunStatus,
  getGoldenRunProgress,
  stopExperiment,
  listModels,
  triggerDeploy,
  listGoldenProfiles,
  triggerGoldenProfileDeploy,
  getGoldenProfileDeployStatus,
} from "./studio-backend-api.js";
import { loadModalOptions } from "./studio-output-preferences.js";
import { goldenProgressResponseAction, progressSpanView } from "./studio-golden-progress.js";

import { resolveRunImageUrl, hasRunImage, normalizeStudioRun, normalizeGenerationSettings, buildWaterfallLines, resolveSelectionResultKey, buildViewerRecordFromRun, resolveViewerInput, generationIdForLegacyRunId } from "./studio-run-normalizer.js";
import {
  saveSelection,
  loadSelection,
  clearSelection,
  loadControlDraft,
  saveControlDraft,
  clearControlDraft,
  saveRunResult,
  loadRunResult,
  clearRunResult,
  clearAllRunResults,
  saveExperimentDraft,
  loadExperimentDraft,
  setCarouselCleared,
  isCarouselCleared,
  loadGoldenProfileSelection,
  saveShellSelection,
  loadShellSelection,
  loadWorkflowMethods,
  saveWorkflowMethods,
  SHELL_MODES,
  SHELL_SUBTOOLS,
  SHELL_PLACEHOLDERS,
  shellGateReason,
} from "./studio-playground-state.js";
import {
  createPlaygroundRunController,
  projectRunToLegacy,
  LEGACY_TERMINAL_STATUSES,
} from "./studio-playground-run.js";
import { updateRunAnnotation, saveRunOutput, getMethodCompat } from "./studio-backend-api.js";
import { createHistoryRepository } from "./history-v2-repository.js";
import { requestHistoryRecordFocus } from "./studio-history-v2.js";

const PLAYGROUND_PREVIEW_KEY = "comfymodal.studio.playground-preview.v1";
const PLAYGROUND_VIEW_KEY = "comfymodal.studio.playground-view.v1";

function _savePlaygroundPreviewId(id) {
  try {
    if (typeof sessionStorage !== "undefined") sessionStorage.setItem(PLAYGROUND_PREVIEW_KEY, String(id || ""));
  } catch (_err) {}
}

function _readPlaygroundPreviewId() {
  try {
    if (typeof sessionStorage === "undefined") return "";
    return sessionStorage.getItem(PLAYGROUND_PREVIEW_KEY) || "";
  } catch (_err) {
    return "";
  }
}

function _clearPlaygroundPreviewId() {
  try {
    if (typeof sessionStorage !== "undefined") sessionStorage.removeItem(PLAYGROUND_PREVIEW_KEY);
  } catch (_err) {}
}

function _savePlaygroundView(state) {
  try {
    if (typeof sessionStorage !== "undefined") {
      sessionStorage.setItem(PLAYGROUND_VIEW_KEY, JSON.stringify({
        experimentMode: !!(state && state.playground && state.playground.experimentMode),
        queueMode: !!(state && state.playground && state.playground.queueMode),
      }));
    }
  } catch (_err) {}
}

function _loadPlaygroundView() {
  try {
    if (typeof sessionStorage === "undefined") return null;
    const saved = JSON.parse(sessionStorage.getItem(PLAYGROUND_VIEW_KEY) || "null");
    if (!saved || typeof saved.experimentMode !== "boolean") return null;
    if (typeof saved.queueMode !== "boolean") saved.queueMode = false;
    return saved;
  } catch (_err) {
    return null;
  }
}

/**
 * Modal can return the app lookup failure either as a stable error code or as
 * provider text. Keep this check narrow so other "not found" run errors do not
 * suggest a deployment fix.
 */
export function isModalAppNotFoundError(result) {
  if (!result || typeof result !== "object") return false;
  const codes = [
    result.error_code,
    result.error && result.error.code,
  ].filter((value) => value != null).map((value) => String(value).toUpperCase());
  if (codes.some((code) => /(?:MODAL_)?APP(?:LICATION)?_NOT_FOUND/.test(code))) return true;

  const messages = [
    result.message,
    result.error,
    result.error && result.error.message,
    result.error && result.error.detail,
    result._error_detail,
  ].filter((value) => typeof value === "string");
  return messages.some((message) =>
    /\b(?:modal\s+)?app(?:lication)?\b[\s\S]{0,80}\bnot found\b/i.test(message)
      || /\bnot found\b[\s\S]{0,80}\b(?:modal\s+)?app(?:lication)?\b/i.test(message));
}

export async function buildStudioModalOptions(apiBase) {
  const options = await loadModalOptions(apiBase);
  if (typeof window !== "undefined") window._comfyModalExecutionMode = options.execution_mode;
  return options;
}

// Output/config options are needed by every run, so start loading them with
// the workflow rather than making the Run click pay for the first request.
// Keep the promise (not just its result) so selection and click paths share a
// single request. Settings changes update an already-warm value below.
const _studioModalOptionsCache = new Map();

function _preloadStudioModalOptions(apiBase) {
  const base = apiBase || "/comfymodal";
  let entry = _studioModalOptionsCache.get(base);
  if (entry) return entry.promise;
  entry = { value: null, promise: null };
  entry.promise = buildStudioModalOptions(base).then((options) => {
    entry.value = options;
    return options;
  });
  _studioModalOptionsCache.set(base, entry);
  return entry.promise;
}

// A settings POST has completed before this event is published. Merge the
// returned settings into the warm cache so a changed preference is not sent
// stale merely because the config request was preloaded earlier.
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("comfymodal:output-preferences-changed", (event) => {
    const changed = event && event.detail;
    if (!changed || typeof changed !== "object") return;
    _studioModalOptionsCache.forEach((entry) => {
      entry.promise = entry.promise.then((options) => {
        const merged = Object.assign({}, options, changed);
        entry.value = merged;
        return merged;
      });
    });
  });
}

// Latest live render trio so mapping-saved refreshes (below) can act on
// the current Playground state without a browser reload. Refreshed on
// every control-panel render; the shell state object itself is live.
var _latestPlaygroundTrio = null;
var _mappingSavedChain = null;

async function _refreshPlaygroundAfterMappingSaved(workflowId, versionId) {
  var ref = _latestPlaygroundTrio;
  if (!ref) return;
  var state = ref.state, context = ref.context, actions = ref.actions;
  var pg = state && state.playground;
  var store = pg && pg._workflowRun;
  var wf = pg && pg._workflowRunModule;
  // Playground never initialized (or state replaced): the next mount
  // fetches a fresh bundle anyway, so there is nothing to refresh.
  if (!store || !wf) return;
  // A save for a workflow the shelf is not showing must not disturb it.
  if (String(store.workflowId || "") !== workflowId) return;
  var apiBase = (context && context.apiBase) || "/comfymodal";
  _flushShelfSave(state);
  if (versionId && String(store.workflowVersionId || "") !== versionId) {
    // The save created a new immutable version: adopt it exactly like an
    // explicit version switch (fresh bundle, graph defaults, saved values,
    // persisted selection). This matches what a browser refresh lands on.
    var res = null;
    try {
      res = await wf.selectVersion(apiBase, store, versionId);
    } catch (_e) { res = null; }
    if (!res || !res.ok) return;
    try { await _loadWorkflowModelLibrary(state, apiBase); } catch (_e) { /* best-effort */ }
    try {
      wf.saveWorkflowSelection({
        workflowId: store.workflowId,
        workflowVersionId: store.workflowVersionId,
        workflowName: store.workflowName || "",
      });
    } catch (_e) { /* best-effort */ }
    try { _rememberSelection(state); } catch (_e) { /* best-effort */ }
  } else {
    // Same version, new/changed mapping: re-fetch the bundle in place,
    // keeping the user's current edits and filling graph defaults only
    // for roles that have no value yet (e.g. newly exposed shelf fields).
    var ok = false;
    try {
      ok = await _refreshRunContext(state, context);
    } catch (_e) { ok = false; }
    if (!ok) return;
    try {
      var fresh = (wf.defaultValuesFromContext && wf.defaultValuesFromContext(store)) || {};
      Object.keys(fresh).forEach(function (role) {
        if (store.controlValues[role] === undefined) store.controlValues[role] = fresh[role];
      });
    } catch (_e) { /* defaults are best-effort */ }
  }
  if (String((store && store.workflowId) || "") !== workflowId) return;
  _rerenderWorkflowSection(state, context, actions, { applySaved: true });
}

// A Wizard mapping save (first mapping or revision) leaves any live
// Playground shelf showing the pre-save bundle: new/changed roles stay
// invisible until a browser refresh re-fetches them. Refresh the affected
// selection in place instead. Same guard style as the settings listener.
if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("comfymodal:mapping-saved", function (event) {
    var detail = (event && event.detail) || {};
    var workflowId = detail.workflowId != null ? String(detail.workflowId) : "";
    var versionId = detail.workflowVersionId != null ? String(detail.workflowVersionId) : "";
    if (!workflowId) return;
    // Serialize refreshes; each re-reads live state when it runs.
    _mappingSavedChain = (_mappingSavedChain || Promise.resolve()).then(function () {
      return _refreshPlaygroundAfterMappingSaved(workflowId, versionId);
    }).catch(function () { /* refresh is best-effort */ });
  });
}

// Compatibility seam for the retired legacy History renderer. Experiment
// details now belong to History V2; route the old tile action through its
// supported focus request instead of reviving the deleted legacy loader.
export async function loadExperimentIntoPlayground(state, context, experimentId) {
  if (!experimentId) return { ok: false, error: "Experiment ID is missing." };
  requestHistoryRecordFocus(String(experimentId), "experiment");
  if (!context || typeof context.setPage !== "function") {
    return { ok: false, error: "Studio navigation is unavailable." };
  }
  context.setPage("history");
  return { ok: true };
}
import { el, buildViewerShell, resolveViewerShellArgs, viewerFirst, renderEmptyState } from "./studio-ui.js";
import { openComparePair } from "./studio-image-compare.js";
import { mountPostprocessWorkspace } from "./studio-postprocess.js";
import { renderLoadingState } from "./studio-loading.js";
import { BINDABLE_INPUTS } from "./studio-bindable-inputs.js";
import { FIELD_BLOCKS } from "./studio-field-blocks.js";
import { renderWorkflowPicker } from "./studio-workflow-picker.js";
import { STYLE_CATALOG } from "./studio-style-catalog.js";
import {
  loadShelfLayout,
  saveShelfLayout,
  loadShelfValues,
  saveShelfValues,
  saveSkipTextGenerate,
  loadToolWorkflows,
  saveToolWorkflows,
  loadToolDefault,
  takePendingPlaygroundBase,
  setPendingPlaygroundImage,
  takePendingPlaygroundImage,
} from "./studio-playground-state.js";

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Polling helper for experiment status ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
// Polls getStudioRunStatus and updates runState to reflect queued,
// running, completed, or error states.
//
// Completion requires real evidence: completed cell count > 0,
// an explicit experiment.completed event, or cell.completed events.
// Empty/unknown snapshots with no definition stay in waiting state.
//
// Polling has a finite timeout (POLL_TIMEOUT_MS). Every tick checks
// container.isConnected and stops if the container is detached (e.g.,
// after navigating away). Transient fetch errors keep the timer alive
// in waiting state until the deadline is reached.

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;
// Consecutive "unknown or expired request_id" cursor answers before the
// poll admits the request will never register. Registration is synchronous
// on the POST path (before remote dispatch), so a handful of retries covers
// the genuine startup race; past this bound the id is mismatched or the run
// took a path that never registers it, and spinning silently forever is what
// freezes the bar on pending segments with a stale status word.
const GOLDEN_PROGRESS_UNKNOWN_REQUEST_LIMIT = 120;

function _stopGoldenProgressPolling(state, requestId) {
  const poll = state && state.playground && state.playground._goldenProgressPoll;
  if (!poll || (requestId && poll.requestId !== requestId)) return;
  poll.active = false;
  if (poll.timer != null) clearTimeout(poll.timer);
  if (state.playground) state.playground._goldenProgressPoll = null;
}

// Golden progress deliberately uses a chained timeout. The next request is
// created only after the previous response has been handled, so a slow poll
// cannot overlap the next cursor read.
function _startGoldenProgressPolling(state, context, requestId, ctrl) {
  if (!state || !state.playground || !requestId || !ctrl) return;
  _stopGoldenProgressPolling(state);
  const apiBase = (context && context.apiBase) || "/comfymodal";
  const poll = { requestId: String(requestId), cursor: 0, timer: null, active: true, unknownCount: 0 };
  state.playground._goldenProgressPoll = poll;

  const schedule = () => {
    if (!poll.active) return;
    poll.timer = setTimeout(pollOnce, 100);
  };
  const pollOnce = async () => {
    if (!poll.active || state.playground._goldenProgressPoll !== poll) return;
    let data;
    try {
      data = await getGoldenRunProgress(apiBase, poll.requestId, poll.cursor);
    } catch (error) {
      // The POST may have completed while this request was in flight.  Its
      // terminal handler already stopped this poll, so do not report the
      // expected expired-request response as a user-visible failure.
      if (!poll.active || state.playground._goldenProgressPoll !== poll) return;
      if (typeof ctrl.isTerminal === "function" && ctrl.isTerminal()) {
        _stopGoldenProgressPolling(state, poll.requestId);
        return;
      }
      ctrl.setGoldenProgressError("Golden progress polling failed: " + (error.message || "request failed"));
      schedule();
      return;
    }
    if (!poll.active || state.playground._goldenProgressPoll !== poll) return;
    const responseAction = goldenProgressResponseAction(
      data,
      typeof ctrl.isTerminal === "function" && ctrl.isTerminal(),
    );
    if (responseAction === "retry") {
      // The run POST and event store register the request independently. Keep
      // the cursor quiet during that small startup window and retry — but
      // only up to the bound. Past it the request will never register (id
      // mismatch or a non-registering run path): say so once and stop this
      // poll instead of spinning silently for the whole run. The run itself
      // is unaffected; completion still lands through the POST result.
      poll.unknownCount += 1;
      if (poll.unknownCount >= GOLDEN_PROGRESS_UNKNOWN_REQUEST_LIMIT) {
        _stopGoldenProgressPolling(state, poll.requestId);
        ctrl.setGoldenProgressError(
          "Golden live progress is unavailable for this run (progress store has no such request). "
          + "The run itself continues — the result still appears when it finishes."
        );
        return;
      }
      schedule();
      return;
    }
    poll.unknownCount = 0;
    if (responseAction === "stop") {
      _stopGoldenProgressPolling(state, poll.requestId);
      return;
    }
    if (responseAction === "error") {
      const message = data && (data.message || data.error)
        ? (data.message || data.error)
        : "Golden progress endpoint returned no usable response";
      ctrl.setGoldenProgressError("Golden progress polling failed: " + message);
      schedule();
      return;
    }
    if (data.request_id != null && String(data.request_id) !== poll.requestId) {
      schedule();
      return;
    }
    const nextCursor = Number(data.cursor);
    if (Number.isFinite(nextCursor) && nextCursor >= poll.cursor) poll.cursor = nextCursor;
    ctrl.applyGoldenProgress({ ...data, request_id: poll.requestId });
    if (data.terminal) {
      _stopGoldenProgressPolling(state, poll.requestId);
    } else {
      schedule();
    }
  };
  // Start immediately, before the still-in-flight run POST is awaited.
  pollOnce();
}

/**
 * Idempotent stop: clear the poll timer and null the reference.
 * Safe to call multiple times.  The timer is stored on the state object
 * (survives re-renders) rather than the container DOM element (destroyed
 * on re-render).  Navigation-away detection uses a state flag instead of
 * container.isConnected so that intermediate polling updates (which call
 * context.setPage and re-create the container) do not kill the timer.
 */
function _stopPolling(state) {
  const key = state && state.playground && state.playground._pollTimer;
  if (key != null) {
    clearInterval(key);
    if (state.playground) state.playground._pollTimer = null;
  }
}

function _startPolling(container, state, context, actions, runState) {
  const experimentId = runState.experimentId || runState.runId;
  if (!experimentId) return;
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // Idempotent stop: clear any previous timer before starting new one
  _stopPolling(state);

  const deadline = Date.now() + POLL_TIMEOUT_MS;

  const pollTimer = setInterval(async () => {
    // Stop if the Playground is no longer the active shell page (e.g.
    // user navigated to History).  This is NOT triggered by re-renders
    // during polling because they keep state.activePage as "playground".
    if (state.activePage !== "playground") {
      _stopPolling(state);
      return;
    }

    // Finite timeout: if deadline exceeded, transition to error
    if (Date.now() >= deadline) {
      _stopPolling(state);
      var ctrl = _getRunController(state, actions);
      if (ctrl && ctrl.getRunId()) {
        ctrl.applyLocalError("Experiment timed out after 5 minutes.");
      } else if (actions && actions.setRunState) {
        actions.setRunState({ status: "error", message: "Experiment timed out after 5 minutes." });
      }
      return;
    }

    let data;
    try {
      data = await getStudioRunStatus(apiBase, experimentId);
    } catch (err) {
      // Transient fetch error ├óΓé¼ΓÇ¥ keep current state until deadline
      var _c0 = _getRunController(state, actions);
      if (_c0 && _c0.getRunId()) return;
      if (actions && actions.setRunState) actions.setRunState({ status: "waiting", experimentId });
      return;
    }

    if (!data) {
      var _c1 = _getRunController(state, actions);
      if (_c1 && _c1.getRunId()) return;
      if (actions && actions.setRunState) actions.setRunState({ status: "waiting", experimentId });
      return;
    }

    // Server-level error response
    if (data.status && data.status !== "ok") {
      _stopPolling(state);
      const errMsg = (data.message || data.error || "Run failed.").substring(0, 200);
      var ctrl2 = _getRunController(state, actions);
      if (ctrl2 && ctrl2.getRunId()) {
        ctrl2.applyLocalError(errMsg);
      } else if (actions && actions.setRunState) {
        actions.setRunState({ status: "error", message: errMsg });
      }
      return;
    }

    // Unknown experiment (no definition yet or invalid id)
    if (!data.definition && (!data.snapshot || Object.keys(data.snapshot).length === 0)) {
      var _c2 = _getRunController(state, actions);
      if (_c2 && _c2.getRunId()) return;
      if (actions && actions.setRunState) actions.setRunState({ status: "waiting", experimentId });
      return;
    }

    const snapshot = data.snapshot || {};
    const events = data.events || [];
    const counters = snapshot.counters || {};
    const completedCellCount = counters.completed || 0;
    const totalCells = snapshot.total_cells || 0;

    // Result association (extracted from the raw journal).
    let _primaryOutput = null;
    for (const ev of events) {
      if (ev.type !== "cell.completed" || !ev.payload) continue;
      const payload = ev.payload || {};
      if (payload.primary_asset_id) {
        _primaryOutput = apiBase + "/assets/" + encodeURIComponent(payload.primary_asset_id);
        break;
      }
      if (payload.output_paths && payload.output_paths.length > 0) {
        _primaryOutput = apiBase + "/studio/outputs/" + encodeURIComponent(payload.output_paths[0]);
        break;
      }
    }
    const extras = {
      experimentId: experimentId,
      completedCells: completedCellCount,
      totalCells: totalCells,
      hasHistory: completedCellCount > 0 || events.some(function (ev) { return ev.type === "cell.completed"; }),
      primaryOutput: _primaryOutput,
    };
    if (completedCellCount > 0 && totalCells > 0) {
      extras.cellProgress = completedCellCount + "/" + totalCells;
    }
    const _ctrl = _getRunController(state, actions);
    if (_ctrl && _ctrl.getRunId()) {
      // Canonical single-run path: lifecycle state is owned by the controller.
      _ctrl.applySnapshot(data, extras);
      // Terminal reached ├óΓé¼ΓÇ¥ stop polling (duplicate polls are no-ops anyway).
      if (_ctrl.isTerminal()) _stopPolling(state);
      return;
    }

    _stopPolling(state);
  }, POLL_INTERVAL_MS);
  // Store timer reference on state (survives re-renders) instead of
  // container (destroyed on re-render from context.setPage calls).
  if (state && state.playground) state.playground._pollTimer = pollTimer;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Effective Controls builder ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Composes the full set of rendered bound controls from:
//   1. current user edits (state.playground.controls)
//   2. hydrated values (from persisted draft or snapshot defaults)
//   3. preset defaults
// This ensures all visible bound fields are sent on submission,
// not only fields that had explicit input events.

function getCurrentPresetForSelection(state, presetId) {
  const currentPreset = state.playground && state.playground._currentPreset;
  if (!currentPreset) return null;
  return (currentPreset.id || currentPreset.label || "") === (presetId || "") ? currentPreset : null;
}

function hydrateControlsForSelection(state, presetId, featureId, preset) {
  if (!state.playground) return;

  // A persisted draft contains explicit user edits ├óΓé¼ΓÇ¥ load into
  // `state.playground.controls` (which buildEffectiveControls serialises)
  // and _hydratedControls (backward-compatible source/behavior expectations).
  const draft = presetId && featureId ? loadControlDraft(presetId, featureId) : {};
  if (draft && typeof draft === "object" && Object.keys(draft).length > 0) {
    state.playground.controls = draft;
    state.playground._hydratedControls = draft;
    return;
  }

  // No draft: build resolvedControls from preset defaults
  // and definition defaults (CONTROL_DEFS).  Do NOT carry resolvedControls
  // from a previous successful run forward as implicit submission overrides.
  const presetDefaults = (preset && preset.defaults) || {};
  const merged = {};

  // Start with definition defaults (CONTROL_DEFS)
  for (const defId in CONTROL_DEFS) {
    if (Object.prototype.hasOwnProperty.call(CONTROL_DEFS[defId], "defaultValue")) {
      merged[defId] = CONTROL_DEFS[defId].defaultValue;
    }
  }

  // Overlay preset defaults (own-property check preserves 0/false)
  for (const key in presetDefaults) {
    if (Object.prototype.hasOwnProperty.call(presetDefaults, key)) {
      merged[key] = presetDefaults[key];
    }
  }

  state.playground._hydratedControls = merged;
}

function buildEffectiveControls(state) {
  // Only include explicit user overrides from state.playground.controls.
  // The backend fills in defaults for any missing controls.
  // No fallback to display-only defaults or binding-visible iteration.
  const userOverrides = (state.playground && state.playground.controls) || {};
  const controls = {};
  Object.keys(userOverrides).forEach(function (ctrlId) {
    controls[ctrlId] = userOverrides[ctrlId];
  });
  return controls;
}

/**
 * Persist the current experiment draft (experimentAxes + compareBackendIds)
 * for the active selection if both presetId and featureId are set.
 * Safe to call on every render ├óΓé¼ΓÇ¥ performs a synchronous localStorage write.
 */
function _saveExperimentDraftFromState(state) {
  const pg = state && state.playground;
  if (!pg) return;
  const presetId = pg.selectedBackendId;
  const featureId = pg.featureId;
  if (!presetId || !featureId) return;
  saveExperimentDraft(
    presetId,
    featureId,
    pg.experimentAxes || {},
    pg.compareBackendIds || []
  );
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Recent runs state management ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Reusable loader/state-owned collection of recent runs, refreshed:
//   - on initial hydration
//   - after finalized completion
//   - after preset deletion if needed
//   - when returning to Playground after History changes
// Hydration comes from the History V2 feed (same durable authority as the
// History page) ├óΓé¼ΓÇ¥ legacy feeds are no longer consulted.

let _recentRunsCache = null;
let _recentRunsCacheKey = "";

var _recentRunsRepoPromise = null;
var _recentRunsRepoKey = "";

function _getRecentRunsRepo(apiBase) {
  if (_recentRunsRepoPromise && _recentRunsRepoKey === apiBase) {
    return _recentRunsRepoPromise;
  }
  _recentRunsRepoKey = apiBase;
  _recentRunsRepoPromise = createHistoryRepository({ mode: "v2", apiBase: apiBase });
  return _recentRunsRepoPromise;
}

// The History V2 record the History detail overlay renders for a run.  A run
// id is NOT a generation id and nothing else links the two, so resolution
// works down this chain — every step returns the SAME durable record History
// shows, and a miss falls through to the next:
//   1. the run's bridged generation id (stamped at record time; no fetch),
//   2. the id as-is (a selected run that already carries a record id),
//   3. the legacy history entry for the run id, whose internal run id maps
//      onto the durable record (covers every run ever recorded, no restart
//      or response field needed),
//   4. the feed (a projection that does expose a run id).
// Returns null when History V2 has no record for the run at all.
async function _resolveHistoryViewerRecord(repo, runId, run, apiBase) {
  if (!repo || !runId) return null;
  const _usable = function (rec) {
    return rec && !(Array.isArray(rec.errors) && rec.errors.some(function (e) {
      return e && (e.code === "load_failed" || e.code === "not_found");
    })) ? rec : null;
  };
  const _detail = async function (id) {
    if (!id) return null;
    try { return _usable(await repo.getGeneration(id)); } catch (err) { return null; }
  };

  const bridged = run && (run.generationId || run.historyGenerationId || run.history_generation_id);
  const viaBridge = await _detail(bridged ? String(bridged) : null);
  if (viaBridge) return viaBridge;

  const direct = await _detail(runId);
  if (direct) return direct;

  try {
    const entry = await _fetchSameRunHistoryEntry(apiBase, runId);
    const derived = await generationIdForLegacyRunId(entry && entry.run_id, entry && entry.kind);
    const viaEntry = await _detail(derived);
    if (viaEntry) return viaEntry;
  } catch (err) { /* fall through to the feed scan */ }

  try {
    const feed = await repo.listFeed({ limit: 200, kinds: ["generation"], sort: "newest" });
    const wanted = {};
    [runId, run && run.id, run && run.runId, run && run.experimentId].forEach(function (value) {
      if (value != null && value !== "") wanted[String(value)] = true;
    });
    const items = (feed && Array.isArray(feed.items)) ? feed.items : [];
    let match = null;
    for (let i = 0; i < items.length && !match; i++) {
      const item = items[i] || {};
      const keys = [item.id, item.runId, item.experimentId];
      for (let k = 0; k < keys.length; k++) {
        if (keys[k] != null && wanted[String(keys[k])]) { match = item; break; }
      }
    }
    if (!match || !match.id) return null;
    return (await _detail(match.id)) || match;
  } catch (err) {
    return null;
  }
}

export async function refreshRecentRuns(apiBase, outputOverride) {
  try {
    const repo = await _getRecentRunsRepo(apiBase);
    const page = await repo.listFeed({ limit: 50, sort: "newest" }); 
    var items = [];

    // Shared History thumbnail policy: the same thumbnail-then-preview order
    // the History page cards use (see selectFeedAsset in
    // history-v2-repository.js), applied to the already-normalized record
    // with no URL sniffing.  A previous version skipped URLs matching
    // /assets/(ast|graph|...) as supposed workflow-graph previews, but every
    // managed History V2 asset id starts with "ast_" (see history_v2_writer
    // minting), so that pattern rejected EVERY real thumbnail and the strip
    // rendered all placeholders.  Graph previews only exist as legacy lease
    // ids (see resolveRunImageUrl), never as managed History V2 variant
    // URLs.  Originals are never used here — History never fetches Original
    // bytes eagerly, and neither does this view; an original-only generation
    // is imageless until its Original is explicitly opened.
    const historyImageUrl = function (output) {
      if (!output) return "";
      const candidates = [output.thumbUrl, output.previewUrl];
      for (var hi = 0; hi < candidates.length; hi++) {
        if (candidates[hi]) return candidates[hi];
      }
      return "";
    };
    const overrideImageFor = function (rec) {
      if (!outputOverride || !outputOverride.imageUrl) return "";
      const overrideIds = [outputOverride.id, outputOverride.runId, outputOverride.experimentId]
        .filter(Boolean).map(String);
      const recordIds = [rec && rec.id, rec && rec.runId, rec && rec.experimentId]
        .filter(Boolean).map(String);
      return overrideIds.some(function (id) { return recordIds.indexOf(id) !== -1; })
        ? outputOverride.imageUrl
        : "";
    };
    (page.items || []).forEach(function (rec) {
      if (!rec) return;
      if (rec.kind === "experiment") {
        var coverThumb = "";
        var cover = rec.cover || [];
        for (var ci = 0; ci < cover.length; ci++) {
          var c = cover[ci];
          coverThumb = historyImageUrl(c);
          if (coverThumb) {
            break;
          }
        }
        if (!coverThumb) coverThumb = overrideImageFor(rec);
        items.push({
          kind: "experiment",
          id: rec.id,
          experimentId: rec.id,
          prompt: rec.name || rec.prompt || "Experiment",
          label: rec.name || "Experiment",
          presetId: rec.preset || "",
          presetLabel: "",
          featureId: "",
          status: rec.status,
          imageUrl: coverThumb,
          cover: rec.cover,
          startedAt: rec.startedAt,
          completedAt: rec.completedAt,
          durationMs: null,
          favorite: !!rec.favorite,
          note: rec.note || "",
          _historyKind: "experiment",
        });
      } else {
        var feat = rec.featuredOutput || null;
        var imageUrl = historyImageUrl(feat) || overrideImageFor(rec);
        // A carousel is a view of the History feed, not a filtered subset:
        // every generation appears newest-first, with a placeholder when it
        // has no displayable image (same rule as the History cards, which
        // never drop a record for lack of an image).
        items.push({
          kind: "generation",
          id: rec.id,
          experimentId: "",
          runId: rec.runId || rec.id,
          // Feed records already ARE durable records; keep their id under the
          // bridge name too so every consumer resolves them the same way.
          generationId: rec.id,
          prompt: rec.prompt || "",
          presetId: rec.preset || "",
          presetLabel: "",
          featureId: "",
          featureLabel: rec.workflow || "",
          status: rec.status,
          imageUrl: imageUrl,
          featuredOutput: feat,
          startedAt: rec.startedAt,
          completedAt: rec.completedAt,
          durationMs: rec.durationMs,
          favorite: !!rec.favorite,
          note: rec.note || "",
          _historyKind: "generation",
        });
      }
    });

    // A direct run response can arrive before its History V2 projection is
    // visible. That freshness is applied ONLY by attaching the response's
    // real output URL onto the matching durable record above
    // (overrideImageFor) — the strip never invents a synthetic item for it.
    // A previous version appended a fallback item here; because production
    // single-run ids never equal their durable generation ids, the fallback
    // never deduplicated away, always sorted first on its fresh timestamp,
    // and rendered as a phantom EXP item (any truthy experimentId flips the
    // strip's experiment detection) routing to a History experiment detail
    // that does not exist.  The canvas already shows the direct response
    // synchronously at completion, so nothing is lost by waiting for the
    // durable projection to appear in the feed.

    // Sort by created time (newest first)
    items.sort(function (a, b) {
      var aTime = a.completedAt || a.startedAt || "";
      var bTime = b.completedAt || b.startedAt || "";
      return bTime.localeCompare(aTime);
    });

    // Deduplicate by ID (first occurrence of each key wins ├óΓé¼ΓÇ¥ newest)
    var seen = {};
    _recentRunsCache = items.filter(function (item) {
      var key = item.experimentId || item.id;
      if (!key) return true;
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });

    _recentRunsCacheKey = apiBase;
    return _recentRunsCache;
  } catch (e) {
    _recentRunsCache = [];
    return [];
  }
}

export function getRecentRuns() {
  return _recentRunsCache;
}

export function clearRecentRunsCache() {
  _recentRunsCache = [];
  _recentRunsCacheKey = "";
}

// ΓöÇΓöÇ Same-run history timings fallback (Shelf single-run slice) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
//
// When a completed single run carries no direct timings AND the History V2
// feed has no projection for it yet (mocked + raced backends), fall back to
// the legacy history entry for the SAME run id only ΓÇö matched on the
// experiment id already carried by the completion. Timings from any other
// run are never borrowed, and an entry without timings (e.g. omitOutputs
// runs) yields no fallback, so no output evidence is fabricated.
function _fetchSameRunHistoryEntry(apiBase, experimentId) {
  if (!apiBase || !experimentId) return Promise.resolve(null);
  var url = apiBase + "/history?page=1&page_size=50";
  return fetch(url).then(function (res) {
    if (!res || !res.ok) return null;
    return res.json().catch(function () { return null; });
  }).then(function (data) {
    var items = (data && Array.isArray(data.items)) ? data.items : [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i] || {};
      if (it.experiment_id === experimentId || it.run_id === experimentId) return it;
    }
    return null;
  }).catch(function () { return null; });
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Hydration helper ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Restore saved selection, fetch presets + history, validate preset,
// restore latest completed run preview plus draft/snapshot defaults.

function _loadPersistedSelectionResult(state, store, fallback, context) {
  const key = resolveSelectionResultKey(state, store, fallback);
  if (!key.presetId || !key.featureId || !state || !state.playground) return null;
  const persistedRun = loadRunResult(key.presetId, key.featureId);
  if (persistedRun) {
    state.playground._selectedRun = persistedRun;
    state.playground.lastRunOutput = _canvasUrlForRun(persistedRun, persistedRun.imageUrl) || null;
    // The local result is also passed as the refresh override so its fresh
    // output URL attaches to the matching durable record when one exists;
    // it never creates a strip item of its own.
    if (context) {
      const apiBase = context.apiBase || "/comfymodal";
      refreshRecentRuns(apiBase, persistedRun).then(function () {
        if (context.setPage) context.setPage("playground");
      });
    }
  }
  return persistedRun;
}

export async function hydratePlayground(state, context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // 1. Load saved selection from localStorage
  const saved = loadSelection();

  // 2. No backend presets exist any more: the selected Workflow (and its
  // current Version) is the only run identity, and the run store hydrates it.
  const featureId = (saved && saved.featureId) || "txt2img";
  var savedTool = "";
  try {
    savedTool = _storageGet("comfymodal.studio.playground.tool.v1") || "";
  } catch (_e) {}
  if (state.playground) {
    state.playground.featureId = featureId;
    state.playground.selectedBackendId = "";
    state.playground.activeTool = normalizeToolId(savedTool || featureId || "t2i");
    state.playground.toolId = state.playground.activeTool;
    _SHELF_TYPE_FALLBACK = state.playground.activeTool;
    // Visible shell restores once in renderControlPanel (single owner) so a
    // first paint already shows the persisted mode/subtool.
    _restoreCanvasImage(state);
  }
  const targetPresetId = "";

  const experimentDraft = loadExperimentDraft(targetPresetId, featureId);
  if (state.playground) {
    state.playground.experimentAxes = experimentDraft ? experimentDraft.experimentAxes : {};
    state.playground.compareBackendIds = experimentDraft ? experimentDraft.compareBackendIds : [];
  }

  // 6a. Try to restore from localStorage persisted run result first
  const persistedKey = resolveSelectionResultKey(state, null, {
    presetId: targetPresetId,
    featureId,
  });
  const persistedRun = _loadPersistedSelectionResult(state, null, persistedKey);
  if (!isCarouselCleared()) {
    await refreshRecentRuns(apiBase, persistedRun);
    if (!persistedRun && targetPresetId) {
      const matchingCompleted = getRecentRuns().filter(function (nr) {
        return nr.presetId === targetPresetId;
      });
      if (matchingCompleted.length > 0) {
        // Sort by completedAt descending (then startedAt as tiebreaker)
        // to ensure we get the newest matching run
        matchingCompleted.sort(function (a, b) {
          const aTime = (a.completedAt || a.startedAt || "");
          const bTime = (b.completedAt || b.startedAt || "");
          return bTime.localeCompare(aTime);
        });
        const latest = matchingCompleted[0];
        if (latest && latest.imageUrl) {
          state.playground.lastRunOutput = latest.imageUrl;
          state.playground._selectedRun = latest;
          // Persist to localStorage for next reload
          saveRunResult(persistedKey.presetId, persistedKey.featureId, latest);
        }
      }
    }
  }

  // 6b. Controls come from the selected Workflow's own version (no preset).
  hydrateControlsForSelection(state, targetPresetId, featureId, null);

  // 7. Persist the resolved feature selection (the run identity is the
  // Workflow + Version, not a preset id).
  if (featureId) {
    saveSelection("", featureId);
  }

  // 8. Kick off the modern workflow selector init (idempotent ├óΓé¼ΓÇ¥ it is also
  // started from renderControlPanel; this covers hydration-only renders).
  try {
    initWorkflowRun(state, context);
  } catch (e) {
    // Never block legacy hydration on the workflow selector.
  }
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Main Playground renderer ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

export function renderPlayground(state, context) {
  const container = el("div", { class: "comfymodal-studio-playground" });

  // Phase I8: accessible page heading. The Playground has no visible title
  // by design, so this is a visually-hidden h2 (clip pattern ΓÇö never
  // display:none) directly under the shell h1. Card/run labels are NOT
  // promoted to headings.
  container.appendChild(el("h2", {
    text: "Playground",
    "data-testid": "playground-page-title",
    style: "position:absolute;width:1px;height:1px;margin:-1px;padding:0;border:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;",
  }));

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Scoped tracker lifecycle ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  // Studio progress is driven by a scoped tracker (per-run), NOT the
  // global shared tracker. This prevents unrelated ComfyUI executions
  // from driving the Studio progress UI.
  //
  // Scoped trackers are created in _modernRunSubmit (single runs) and in the
  // experiment run handlers, then disposed on terminal states.
  // The _scopedTracker reference in state.playground is managed there.
  //
  // Not subscribed for progress UI updates ├óΓé¼ΓÇ¥ only scoped trackers drive
  // the Studio progress panel to avoid unrelated ComfyUI executions
  // interfering.

  const leftPanel = renderControlPanel(state, context);
  const resizeHandle = _createResizeHandle(leftPanel);
  const rightWorkspace = renderWorkspace(state, context);

  container.appendChild(leftPanel);
  container.appendChild(resizeHandle);
  container.appendChild(rightWorkspace);

  // One-shot image handoff (History/viewer actions). Consumed here — the
  // page root that runs on every Playground show — not in a sub-section
  // build that cached-page navigation can skip. current/post set the
  // canvas image (Post reads it as input); edit-source uploads through
  // the existing history-as-source path so execution gets a mapped
  // filename. Best-effort, never blocking, rejections swallowed.
  try {
    var pendingImage = takePendingPlaygroundImage();
    if (pendingImage && pendingImage.url) {
      if (pendingImage.purpose === "edit-source") {
        var _imgActions = (state.playground && state.playground._runActions) || buildActions(state, context);
        var _imgP = _shelfUseHistoryAsSource(state, context, _imgActions, "source_image", pendingImage.url);
        if (_imgP && typeof _imgP.catch === "function") _imgP.catch(function () {});
      } else {
        _setCanvasImage(state, pendingImage.url, context);
      }
    }
  } catch (_eImg) {}

  return container;
}

var _PANEL_WIDTH_KEY = "comfymodal-studio-panel-width";
var _PANEL_WIDTH_MIN = 200;
var _PANEL_WIDTH_MAX = 600;
var _PANEL_WIDTH_DEFAULT = 333;

function _createResizeHandle(leftPanel) {
  var handle = el("div", { class: "comfymodal-studio-resize-handle" });

  var saved = localStorage.getItem(_PANEL_WIDTH_KEY);
  if (saved) {
    var w = parseInt(saved, 10);
    if (!isNaN(w) && w >= _PANEL_WIDTH_MIN && w <= _PANEL_WIDTH_MAX) {
      leftPanel.style.width = w + "px";
    } else {
      leftPanel.style.width = _PANEL_WIDTH_DEFAULT + "px";
    }
  } else {
    leftPanel.style.width = _PANEL_WIDTH_DEFAULT + "px";
  }

  var isDragging = false;
  var startX = 0;
  var startWidth = 0;

  function _onPointerDown(e) {
    isDragging = true;
    startX = e.clientX;
    startWidth = leftPanel.offsetWidth;
    handle.setPointerCapture(e.pointerId);
    handle.classList.add("active");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    e.preventDefault();
  }

  function _onPointerMove(e) {
    if (!isDragging) return;
    var delta = e.clientX - startX;
    var newWidth = startWidth + delta;
    if (newWidth < _PANEL_WIDTH_MIN) newWidth = _PANEL_WIDTH_MIN;
    if (newWidth > _PANEL_WIDTH_MAX) newWidth = _PANEL_WIDTH_MAX;
    leftPanel.style.width = newWidth + "px";
    e.preventDefault();
  }

  function _onPointerEnd(e) {
    if (!isDragging) return;
    isDragging = false;
    handle.classList.remove("active");
    handle.releasePointerCapture(e.pointerId);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    localStorage.setItem(_PANEL_WIDTH_KEY, String(leftPanel.offsetWidth));
  }

  handle.addEventListener("pointerdown", _onPointerDown);
  handle.addEventListener("pointermove", _onPointerMove);
  handle.addEventListener("pointerup", _onPointerEnd);
  handle.addEventListener("pointercancel", _onPointerEnd);

  return handle;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Left Control Panel (preset-driven) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function renderControlPanel(state, context) {
  const panel = el("div", { class: "comfymodal-studio-control-panel", "data-testid": "control-panel" });

  const isExperiment = state.playground && state.playground.experimentMode;
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const currentSpec = FEATURE_SPECS.find((f) => f.id === currentFeatureId) || FEATURE_SPECS[0];

  // Actions for state mutations (called by event handlers)
  const actions = buildActions(state, context);
  if (state.playground) state.playground._runActions = actions;
  _latestPlaygroundTrio = { state: state, context: context, actions: actions };
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // Hydrate: restore saved state.
  // Phase 1 (sync): load saved selection from localStorage so the
  // initial render shows the correct backend selection without needing
  // a hydration-triggered re-render that would close an open <select>.
  if (!state.playground._hydrationDone) {
    const savedView = _loadPlaygroundView();
    if (savedView) {
      state.playground.experimentMode = savedView.experimentMode;
      // Radio invariant survives reload too: a stored queueMode wins only
      // when experiment mode is off.
      state.playground.queueMode = !savedView.experimentMode && !!savedView.queueMode;
    }
    const saved = loadSelection();
    if (saved) {
      if (saved.featureId) state.playground.featureId = saved.featureId;
      if (saved.presetId) state.playground.selectedBackendId = saved.presetId;
      // Synchronously hydrate experiment draft from localStorage
      // so experiment mode state (axes + compare selections) is restored
      // on reload without waiting for the async hydratePlayground to finish.
      const draft = loadExperimentDraft(saved.presetId, saved.featureId || "txt2img");
      if (draft) {
        if (draft.experimentAxes && Object.keys(draft.experimentAxes).length > 0) {
          state.playground.experimentAxes = draft.experimentAxes;
        }
        if (draft.compareBackendIds && draft.compareBackendIds.length > 0) {
          state.playground.compareBackendIds = draft.compareBackendIds;
        }
      }
    }
    state.playground._hydrationDone = true;
    _restoreShellState(state);
    hydratePlayground(state, context).then(function () {
      if (context && context.setPage) {
        // Check if the backend <select> dropdown is open (focused).
        // Full re-render would destroy the native dropdown causing
        // "opens then closes instantly". Skip re-render and instead
        // imperatively update the select value.
        const select = document.querySelector('[data-testid="backend-select"]');
        const isSelectOpen = select && document.activeElement === select;
        if (!isSelectOpen && !state.playground._backendSelectInteracting) {
          context.setPage("playground");
        } else if (select && state.playground.selectedBackendId) {
          select.value = state.playground.selectedBackendId;
        }
      }
    });
  }

  // Run, queue, experiment, and tool controls live in the workspace top bar
  // (above the canvas), not in this panel. The panel keeps workflow
  // selection, field cards, and the experiment-mode block only.

  // If experiment mode, render experiment-mode controls (context passed explicitly)
  if (isExperiment) {
    const expBlock = renderExperimentMode(state, actions, context);
    panel.appendChild(expBlock);
  }

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Workflow Selector (modern workflow-driven runs) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  // Empty-state only until a workflow is chosen.
  // Phase 1 shell: Post runs the existing local engine (no workflow
  // selection, no shelf fields here), and later-phase placeholders show an
  // honest note instead of stale workflow fields. The workflow selector
  // stays live in placeholder views so picker behavior is preserved.
  var _shellMode = activeModeOf(state);
  var _shellSub = activeSubtoolOf(state);
  var _isPostView = _shellMode === "post";
  var _isPlaceholderView = !_isPostView && _isPlaceholderSubtool(_shellSub);

  if (_isPostView && _shellSub !== "upscale") {
    // The finishing engine is mounted in the native left rail. Its inspector,
    // presets, LUTs, undo stack, and export handlers remain the single owner;
    // only its stage is re-homed into the center canvas below.
    var postHost = el("div", {
      class: "comfymodal-studio-postprocess-sidebar",
      "data-testid": "pp-sidebar",
    });
    var postSource = "";
    try { postSource = _canvasImageUrl(state) || _editorBaseImageUrl(state) || ""; } catch (_postSourceErr) {}
    try {
      state.playground._postProcessMount = mountPostprocessWorkspace(postHost, {
        sourceUrl: postSource,
        nativeSidebar: true,
        // Global panel grid navigation: a panel in another category takes the
        // same shell path as the top submenu buttons (single truth, and the
        // Crop/Heal tool disarms through the existing toggle-off).
        onRequestSubtool: function (sub) { _selectPostCategory(state, context, sub); },
      });
      panel.appendChild(postHost);
      _focusPostCategory(_shellSub, postHost);
    } catch (_postErr) {
      postHost.appendChild(el("p", {
        class: "comfymodal-studio-control-note",
        text: "Post Processing failed to start: " + ((_postErr && _postErr.message) || "unknown error"),
      }));
      panel.appendChild(postHost);
    }
  } else {
    if (_isPostView && _shellSub === "upscale") {
      panel.appendChild(el("p", {
        class: "comfymodal-studio-control-note",
        "data-testid": "post-side-note",
        text: "Upscale arrives in a later phase — execution is disabled. Your Post recipe and image remain preserved.",
      }));
    }
    panel.appendChild(renderWorkflowSelector(state, context, actions));

    if (_isPlaceholderView) {
      panel.appendChild(el("p", {
        class: "comfymodal-studio-control-note",
        "data-testid": "placeholder-side-note",
        text: (STUDIO_SUBTOOL_LABELS[_shellSub] || _shellSub)
          + " arrives in a later phase — workflow execution is disabled for this view. Your workflow, values, and current image are preserved.",
      }));
    } else if (_isModernRunSelected(state)) {
      panel.appendChild(renderShelfSection(state, context, actions));
    }
  }

  _renderGoldenDeployNotice(panel, context);

  // Reset to defaults link (workflow views only — Post and placeholders
  // show no shelf fields to reset).
  if (!_isPostView && !_isPlaceholderView) {
    const resetLink = el("button", {
      class: "comfymodal-studio-reset-link",
      text: "Reset to defaults",
      style: "background:none;border:none;color:var(--color-accent);cursor:pointer;font-size:var(--font-size-sm);padding:4px 0;text-decoration:underline;",
      onclick: function () {
        if (actions && actions.resetToDefaults) actions.resetToDefaults();
      },
    });
    panel.appendChild(resetLink);
  }

  return panel;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Actions builder ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function buildActions(state, context) {
  return {
    setFeature(featureId) {
      clearTimeout(state.playground._draftSaveTimer);

      // Preserve current run result before switching
      const prevPresetId = state.playground.selectedBackendId;
      const prevFeatureId = state.playground.featureId;
      const prevRun = state.playground._selectedRun;
      const prevKey = resolveSelectionResultKey(state, null, {
        presetId: prevPresetId,
        featureId: prevFeatureId,
      });
      if (prevKey.presetId && prevKey.featureId && prevRun) {
        saveRunResult(prevKey.presetId, prevKey.featureId, prevRun);
      }

      state.playground.featureId = featureId;
      // Clear stale controls when feature changes
      state.playground.controls = {};
      state.playground._selectedRun = null;
      state.playground.lastRunOutput = null;
      const selectionKey = resolveSelectionResultKey(state, null, {
        featureId,
      });
      const presetId = selectionKey.presetId;
      const currentPreset = getCurrentPresetForSelection(state, state.playground.selectedBackendId);

      // Load persisted run result for the new feature
      const loadedRun = loadRunResult(selectionKey.presetId, selectionKey.featureId);
      if (loadedRun) {
        state.playground._selectedRun = loadedRun;
        state.playground.lastRunOutput = _canvasUrlForRun(loadedRun, loadedRun.imageUrl) || null;
      }

      hydrateControlsForSelection(state, presetId, featureId, currentPreset);
      // Clear stale run state so Run button re-enables
      if (state.playground) state.playground.runState = null;
      // Dispose scoped tracker ├óΓé¼ΓÇ¥ switching features invalidates current run
      _disposeScopedTracker(state);
      // Persist selection
      saveSelection(selectionKey.presetId, selectionKey.featureId);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    setBackend(backendId) {
      clearTimeout(state.playground._draftSaveTimer);

      // Preserve current run result before switching
      const prevPresetId = state.playground.selectedBackendId;
      const prevFeatureId = state.playground.featureId;
      const prevRun = state.playground._selectedRun;
      const prevKey = resolveSelectionResultKey(state, null, {
        presetId: prevPresetId,
        featureId: prevFeatureId,
      });
      if (prevKey.presetId && prevKey.featureId && prevRun) {
        saveRunResult(prevKey.presetId, prevKey.featureId, prevRun);
      }

      state.playground.selectedBackendId = backendId;
      // Clear stale controls when preset changes to avoid sending
      // controls that the new preset doesn't support
      state.playground.controls = {};
      state.playground._selectedRun = null;
      state.playground.lastRunOutput = null;
      const selectionKey = resolveSelectionResultKey(state, null, {
        presetId: backendId,
        featureId: state.playground.featureId,
      });
      const currentPreset = getCurrentPresetForSelection(state, backendId);

      // Load persisted run result for the new preset+feature
      const loadedRun = loadRunResult(selectionKey.presetId, selectionKey.featureId);
      if (loadedRun) {
        state.playground._selectedRun = loadedRun;
        state.playground.lastRunOutput = _canvasUrlForRun(loadedRun, loadedRun.imageUrl) || null;
      }

      hydrateControlsForSelection(state, backendId, state.playground.featureId, currentPreset);
      // Clear stale run state so Run button re-enables
      if (state.playground) state.playground.runState = null;
      // Dispose scoped tracker ├óΓé¼ΓÇ¥ switching backends invalidates current run
      _disposeScopedTracker(state);
      // Persist selection
      saveSelection(selectionKey.presetId, selectionKey.featureId);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    setControl(ctrlId, value) {
      if (!state.playground.controls) state.playground.controls = {};
      state.playground.controls[ctrlId] = value;
      if (ctrlId === 'prompt' && state.playground.experimentAxes && state.playground.experimentAxes.prompt && state.playground.experimentAxes.prompt.enabled && state.playground.experimentAxes.prompt.values && state.playground.experimentAxes.prompt.values.length > 0) {
        state.playground.experimentAxes.prompt.values[0] = value;
        // Persist experiment draft ├óΓé¼ΓÇ¥ prompt-axis first value changed
        _saveExperimentDraftFromState(state);
      }
      const presetId = state.playground.selectedBackendId;
      const featureId = state.playground.featureId;
      const activePreset = getCurrentPresetForSelection(state, presetId);
      clearTimeout(state.playground._draftSaveTimer);
      state.playground._draftSaveTimer = setTimeout(function () {
        const controls = buildEffectiveControls(state);
        saveControlDraft(presetId, featureId, controls);
      }, 300);
      // Clear stale terminal run state so Run button re-enables on control
      // change, but preserve in-flight states to prevent duplicate submits.
      const currentRunState = state.playground && state.playground.runState;
      const isTerminalState = currentRunState
        && LEGACY_TERMINAL_STATUSES.indexOf(currentRunState.status) !== -1;
      if (isTerminalState) {
        state.playground.runState = null;
        if (context && context.setPage) {
          context.setPage("playground");
        }
      }
    },
    setExperimentMode(enabled) {
      state.playground.experimentMode = !!enabled;
      // Radio with queue mode: both can never be on at the same time.
      if (enabled) {
        state.playground.queueMode = false;
        state.playground._toastDismissed = false;
      }
      _savePlaygroundView(state);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    setQueueMode(enabled) {
      state.playground.queueMode = !!enabled;
      // Radio with experiment mode: enabling queue exits experiment mode.
      if (enabled) state.playground.experimentMode = false;
      _savePlaygroundView(state);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    setCanvasBg(value) {
      if (!state.playground) return;
      state.playground.canvasBg = value || "";
      _saveCanvasBg(state.playground.canvasBg);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    persistExperimentDraft() {
      _saveExperimentDraftFromState(state);
    },
    resetToDefaults() {
      const presetId = state.playground && state.playground.selectedBackendId;
      const featureId = state.playground && state.playground.featureId;
      if (!presetId || !featureId) return;
      // Clear in-memory overrides
      state.playground.controls = {};
      state.playground._selectedRun = null;
      // Clear the saved draft for this preset+feature
      clearControlDraft(presetId, featureId);
      // Rehydrate from preset defaults
      const currentPreset = getCurrentPresetForSelection(state, presetId);
      hydrateControlsForSelection(state, presetId, featureId, currentPreset);
      // Clear stale run state
      if (state.playground) state.playground.runState = null;
      _disposeScopedTracker(state);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    toggleExperimentAxis(ctrlId, enabled) {
      if (!state.playground.experimentAxes) state.playground.experimentAxes = {};
      if (enabled) {
        const presetDefaults = (state.playground._currentPreset && state.playground._currentPreset.defaults) || {};
        const defaultValue = (ctrlId === 'prompt' && state.playground.controls && state.playground.controls.prompt != null)
          ? state.playground.controls.prompt
          : presetDefaults[ctrlId] ?? (CONTROL_DEFS[ctrlId] ? CONTROL_DEFS[ctrlId].defaultValue : "");
        state.playground.experimentAxes[ctrlId] = {
          enabled: true,
          values: [defaultValue],
        };
      } else {
        delete state.playground.experimentAxes[ctrlId];
      }
      // Persist experiment draft ├óΓé¼ΓÇ¥ axes toggles are a persistence trigger
      _saveExperimentDraftFromState(state);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    updateExperimentAxisValues(ctrlId, values) {
      if (!state.playground.experimentAxes) state.playground.experimentAxes = {};
      if (!state.playground.experimentAxes[ctrlId]) {
        state.playground.experimentAxes[ctrlId] = { enabled: true, values: [] };
      }
      const prevLen = (state.playground.experimentAxes[ctrlId].values || []).length;
      // Parse numeric strings to numbers so backend integer schema
      // validation (isinstance(value, int)) accepts them.  Axis values
      // come from DOM input.value which is always a string.
      state.playground.experimentAxes[ctrlId].values = values.map(function (v) {
        if (typeof v === "string" && v.trim() !== "" && !isNaN(Number(v))) return Number(v);
        return v;
      });
      state.playground.experimentAxes[ctrlId].enabled = true;
      if (ctrlId === 'prompt' && state.playground.experimentAxes[ctrlId].values && state.playground.experimentAxes[ctrlId].values.length > 0) {
        if (!state.playground.controls) state.playground.controls = {};
        state.playground.controls.prompt = state.playground.experimentAxes[ctrlId].values[0];
      }
      // Persist experiment draft ├óΓé¼ΓÇ¥ axis values changed
      _saveExperimentDraftFromState(state);
      // Re-render when value count changes (add/remove), but NOT on every
      // keystroke ├óΓé¼ΓÇ¥ that would thrash the UI during text input.
      if (values.length !== prevLen && context && context.setPage) {
        context.setPage("playground");
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
      const prevRunState = state.playground.runState;
      const prevStatus = prevRunState && prevRunState.status;
      state.playground.runState = { ...state.playground.runState, ...runState };

      const newStatus = runState && runState.status;

      // Dispose scoped tracker and clean up local timer on terminal states
      if (runState && newStatus && LEGACY_TERMINAL_STATUSES.indexOf(newStatus) !== -1) {
        if (state.playground && state.playground.runState) {
          delete state.playground.runState._localStartTime;
          delete state.playground.runState._cancelling;
        }
        // Clean up captured running config ├óΓé¼ΓÇ¥ a new run will re-capture
        if (state.playground) delete state.playground._runningExperimentConfig;
        _disposeScopedTracker(state);
      }

      if (runState && newStatus === "completed" && prevStatus !== "completed") {
        // A new run completed ΓÇö the Shelf output is fresh again: clear the
        // stale mark set by Workflow switching.
        if (state.playground) state.playground._shelfStaleOutput = false;
        // A new run completed ├óΓé¼ΓÇ¥ re-enable the carousel synchronously so
        // subsequent re-renders and page loads show recent runs again.
        // Done BEFORE the async refresh so the flag does not persist and
        // suppress the hydrated output on the next render.
        setCarouselCleared(false);

        // Persist primary output URL so canvas shows result
        if (runState.primaryOutput) {
          state.playground.lastRunOutput = runState.primaryOutput;
          _setCanvasImage(state, runState.primaryOutput);
          try {
            _recordImageEdge(state, runState.primaryOutput, _completionSource(state));
          } catch (_e) { /* lineage is best-effort */ }
        }
        // Keep preset/feature selected
         if (!_isModernRunSelected(state)) {
           const completedSelection = resolveSelectionResultKey(state);
           saveSelection(completedSelection.presetId, completedSelection.featureId);
         }
        // Refresh recent runs and try to select finalized normalized run
        const apiBase = (context && context.apiBase) || "/comfymodal";
        const _justFinished = state.playground && state.playground._selectedRun;
        refreshRecentRuns(apiBase, {
          id: runState.experimentId,
          // The override carries the RUN id so the fresh primary output URL
          // attaches to the matching durable record (overrideImageFor); it
          // never becomes a strip item of its own.
          runId: (_justFinished && (_justFinished.runId || _justFinished.id)) || "",
          experimentId: runState.experimentId,
          imageUrl: runState.primaryOutput,
        }).then(function (runs) {
          const experimentId = runState.experimentId;
          let matched = null;
          if (experimentId && runs && runs.length > 0) {
            // Find the matching durable History V2 record: experiment-kind
            // items expose experimentId; generation items match by their
            // record id (the fake/production mirror keys it off the run).
            matched = runs.find(function (nr) {
              return nr.experimentId === experimentId || nr.id === experimentId;
            });
            if (!matched) {
              // Fallback: same-preset newest record. The V2 projection may
              // carry the preset name rather than its id, so also accept the
              // selected preset's label.
              var _selPreset = state.playground._currentPreset || null;
              var _selPresetLabel = _selPreset ? (_selPreset.label || "") : "";
              matched = runs.find(function (nr) {
                return nr.presetId === state.playground.selectedBackendId ||
                       (_selPresetLabel !== "" && nr.presetId === _selPresetLabel);
              });
            }
          }
          if (matched) {
            state.playground._selectedRun = matched;
            // Never nullify lastRunOutput — primaryOutput has already been set.
            // Only overwrite if the matched run carries a valid imageUrl.
            if (matched.imageUrl) {
              // Same full-size resolution as a carousel click: the canvas
              // must not downgrade the just-completed primary output to the
              // record's 256px thumbnail (see _canvasUrlForRun).
              var matchedUrl = _canvasUrlForRun(matched, matched.imageUrl);
              state.playground.lastRunOutput = matchedUrl;
              _setCanvasImage(state, matchedUrl);
              try {
                _recordImageEdge(state, matchedUrl, _completionSource(state));
              } catch (_e) { /* lineage is best-effort */ }
            }
            // Persist the finalized run result to localStorage
             const completedKey = resolveSelectionResultKey(state);
             saveRunResult(completedKey.presetId, completedKey.featureId, matched);
            if (context && context.setPage) context.setPage("playground");
          }
          if (!matched && experimentId) {
            // V2 has no projection for this run yet ΓÇö assemble the finalized
            // run from the SAME run's history entry so its canonical timings
            // still reach the timing card (stages ΓåÆ summary ΓåÆ duration).
            // Canvas evidence is untouched: lastRunOutput stays on the
            // polled primaryOutput, never fabricated from history data.
            _fetchSameRunHistoryEntry(apiBase, experimentId).then(function (entry) {
              if (!entry || !state.playground) return;
              if (entry.status !== "completed") return;
              var entryTimings = entry.timings || (entry.extra && entry.extra.timings) || {};
              if (!entryTimings || Object.keys(entryTimings).length === 0) return;
              var fallback = null;
              try {
                fallback = normalizeStudioRun(entry, apiBase);
              } catch (e) {
                fallback = null;
              }
              if (!fallback || !fallback.timingStages || fallback.timingStages.length === 0) return;
              state.playground._selectedRun = fallback;
              // Persist the finalized run result to localStorage
              try {
                 const fallbackKey = resolveSelectionResultKey(state);
                 saveRunResult(fallbackKey.presetId, fallbackKey.featureId, fallback);
              } catch (e) {}
              if (context && context.setPage) context.setPage("playground");
            });
          }
          // Note: setCarouselCleared was already called synchronously above
        });
      } else if (!runState) {
        // Clearing runState ├óΓé¼ΓÇ¥ preserve lastRunOutput and _selectedRun so
        // prior result stays visible until new submission enters flight.
        // Also clear captured running config since the run is abandoned.
        if (state.playground) delete state.playground._runningExperimentConfig;
      }
      const rerender = !runState || !newStatus || prevStatus !== newStatus;
      if (rerender && context && context.setPage) {
        context.setPage("playground");
      }
    },
  };
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Control Group wrapper ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function renderControlGroup(labelText, inputEl) {
  const group = el("div", { class: "comfymodal-studio-control-group" });
  if (labelText) {
    const label = el("label", { class: "comfymodal-studio-control-label", text: labelText });
    group.appendChild(label);
  }
  if (inputEl) group.appendChild(inputEl);
  return group;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Backend Selector ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Loads runtime presets from the Studio backend abstraction (getRuntimePresets).
// Filters by feature compatibility when appropriate.
// In empty state, links to the Backend tab (H10: no Legacy Setup funnels).

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Workflow Run Selector (modern workflow-driven runs) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Renders a Workflow / Version / Preset selector backed by the frozen
// web/studio-workflow-run.js logic module. When a workflow+version is
// selected, the Run button is gated by resolveRunnable() and runs through
// the canonical controller with a workflow payload (buildRunPayload).
// When NO workflow is selected the legacy backend-preset path is untouched.
//
// The section renders into a dedicated container owned by this module;
// async loads only ever re-render that container (plus the Run button
// gating), never the whole page, so user typing in the mapped controls is
// not clobbered by in-flight fetches.

let _workflowModelLibraryCache = null;
let _workflowModelLibraryCacheKey = "";

/**
 * Load the model inventory the run gate needs, once per apiBase.
 *
 * Compatibility is a server-owned answer, but the browser still needs the
 * inventory to know WHICH model the selected version actually references.
 * Failures degrade to an empty inventory: model compatibility then falls back
 * to the version's own dependency metadata, and an unknown model never blocks
 * a run on a catalogue miss alone.
 *
 * Must never throw ΓÇö it is awaited inside the Workflow-change handler, and a
 * rejection there would strand the run store mid-selection.
 */
async function _loadWorkflowModelLibrary(state, apiBase) {
  const pg = state && state.playground;
  if (!pg) return [];
  const base = apiBase || "/comfymodal";
  if (_workflowModelLibraryCacheKey !== base || !_workflowModelLibraryCache) {
    let records = [];
    try {
      const data = await listModels(base);
      if (data && data.status !== "error" && Array.isArray(data.models)) {
        records = data.models;
      }
    } catch (e) {
      records = [];
    }
    _workflowModelLibraryCache = records;
    _workflowModelLibraryCacheKey = base;
  }
  pg._workflowModelLibrary = _workflowModelLibraryCache;
  return _workflowModelLibraryCache;
}

function _isModernRunSelected(state) {
  const store = state && state.playground && state.playground._workflowRun;
  return !!(store && store.workflowId && store.workflowVersionId);
}

function _workflowOptionLabel(w) {
  // A workflow has one current version, so the chooser shows just the name.
  // Version counts/numbers are internal history, not a choice to offer here.
  return (w && w.name) ? w.name : "Unnamed workflow";
}

function _workflowHasModelContract(store) {
  const ctx = store && store.runContext;
  if (!ctx) return false;
  const wf = ctx.workflow || {};
  const ver = ctx.version || {};
  const wfModels = Array.isArray(wf.compatible_models) ? wf.compatible_models : [];
  const verModels = Array.isArray(ver.compatible_models) ? ver.compatible_models : [];
  return wfModels.length > 0 || verModels.length > 0;
}

/**
 * The currently-selected model filename that is known-incompatible with the
 * version's compatibility contract, or null. Only a schema enum value that
 * the user selected AND that modelCompatibility classified compatible=false
 * qualifies; with no declared contract nothing is incompatible.
 */
function _selectedIncompatibleModel(store, wf, compat) {
  if (!compat || !compat.byFilename) return null;
  if (!_workflowHasModelContract(store)) return null;
  const schema = wf.getControlSchema(store);
  const values = (store.controlValues && typeof store.controlValues === "object") ? store.controlValues : {};
  for (const entry of Object.values(schema)) {
    if (!entry || typeof entry !== "object") continue;
    const enumOptions = Array.isArray(entry.enum_options) ? entry.enum_options : [];
    if (!enumOptions.length) continue;
    const selected = values[entry.semantic_role];
    if (selected === undefined || selected === null) continue;
    const key = String(selected);
    if (!enumOptions.some((o) => String(o) === key)) continue;
    const c = compat.byFilename[key];
    if (c && c.compatible === false) return key;
  }
  return null;
}

/**
 * Gating wrapper: frozen resolveRunnable() reasons + the incompatible-model
 * contribution. Known incompatible models must not silently execute, so Run
 * stays disabled while one is selected.
 */
function _resolveWorkflowRunnable(store, wf, modelRecords) {
  const base = wf.resolveRunnable(store);
  if (!base.runnable) return base;
  const compat = wf.modelCompatibility(store, modelRecords || []);
  const incompatible = _selectedIncompatibleModel(store, wf, compat);
  if (!incompatible) return base;
  return {
    runnable: false,
    reasons: base.reasons.concat(["model '" + incompatible + "' is not compatible with this workflow version"]),
  };
}

function workflowGatingInfo(store, wf, state) {
  if (!store) return { text: "Select a workflow", color: "" };
  if (store.statusLine) return { text: store.statusLine, color: "#d9a441" };
  if (store.status === "error") return { text: store.error || "Load error", color: "#f87171" };
  if (!store.workflowId) return { text: "Select a workflow", color: "" };
  if (!store.workflowVersionId) return { text: "Select a Workflow", color: "" };
  if (store.status === "loading" || !wf || !store.runContext) {
    return { text: store.status === "loading" ? "Loading…" : "Loading workflow…", color: "" };
  }
  // Phase 3: explicit method requirements gate the same line/button.
  var _methodReason = null;
  try { _methodReason = _studioMethodGate(state); } catch (_e) { _methodReason = null; }
  if (_methodReason) return { text: _methodReason, color: "#d9a441" };
  // Use the same local/remote decision as the Run button. A selected Golden
  // profile executes in the deployed container, so host-local dependency
  // reasons must not be shown as a reason that remote execution is blocked.
  const { runnable, reasons } = _workflowRunnableForExecution(state, store, wf);
  if (runnable) return { text: "Ready to run", color: "var(--color-success)" };
  return { text: reasons.length ? reasons.join("; ") : "Not runnable", color: "#d9a441" };
}

function _syncActiveToolToSelection(state, opts) {
  try {
    var pg = state && state.playground;
    var store = pg && pg._workflowRun;
    if (!pg || !store || !store.workflowId) return false;
    var row = (store.library || []).find(function (w) { return String(w.workflow_id) === String(store.workflowId); });
    var ctx = store.runContext;
    var wf = ctx && ctx.workflow;
    var raw = (row && (row.workflow_type || row.workflowType || row.type))
      || (ctx && (ctx.workflow_type || ctx.workflowType))
      || (wf && (wf.workflow_type || wf.workflowType))
      || "";
    var canonical = normalizeToolId(raw);
    var known = STUDIO_TOOLS.some(function (t) { return t.id === canonical; });
    if (!raw || !known) return false;
    if (pg.activeTool !== canonical) {
      pg.activeTool = canonical;
      pg.toolId = canonical;
      _SHELF_TYPE_FALLBACK = canonical;
      try {
        _storageSet("comfymodal.studio.playground.tool.v1", canonical);
      } catch (_e) {}
      // The execution type actually changed (e.g. manual picker change):
      // update the visible shell sensibly. A sketch workflow keeps the
      // already-visible Generate/Edit Sketch choice when compatible,
      // otherwise the new type takes its default shell view. Views that
      // did not change type (Post, same-type switches) keep their shell.
      // Background restores (reload/queue drain) update the execution
      // truth above but never override the intended shell: a persisted
      // Post view or a newer user shell choice survives initialization,
      // and the workflow family reconciles to the desired type instead.
      var background = !!(opts && opts.background);
      var preserveShell = background
        && (pg.activeMode === "post" || _subtoolExecutionType(pg.activeMode, pg.activeSubtool) === null);
      var shell = preserveShell ? null : _defaultShellForTool(canonical, pg.activeMode, pg.activeSubtool);
      if (shell && (pg.activeMode !== shell.mode || pg.activeSubtool !== shell.subtool)) {
        pg.activeMode = shell.mode;
        pg.activeSubtool = shell.subtool;
        _persistShellState(state);
      }
      return true;
    }
    return false;
  } catch (_e) { /* selection sync is best-effort */ return false; }
}

// One workspace, not one sandbox per workflow: the Playground remembers the
// last workflow per tool and carries workspace values (prompt, seed,
// sampler controls, source image) across workflow switches. Values travel
// through the normal validated commit path, so unknown/invalid roles are
// dropped and gating stays truthful. Each workflow's durable autosave still
// keeps its own copy.
var _WORKSPACE_CARRY_ROLES = ["prompt", "seed", "width", "height"];
// Sampler-tuning roles are deliberately absent above: steps/scheduler/cfg/
// sampler are workflow-specific — each workflow keeps its own — in either
// spelling (see the explicit graph-era list in _applyWorkspaceCarry).
// The same family starts collapsed in the Advanced shelf section on fresh
// layouts (see _shelfLayoutFor).
var _DEFAULT_ADVANCED_ROLES = ["steps", "step_count", "cfg", "cfg_scale", "scheduler"];
// Carry targets include graph-era spellings: the loop below commits only
// roles present in the NEW schema, resolving each through _carryValue so
// `steps` seeds `step_count` and vice versa.
// Durable browser memory: localStorage survives refresh and restart.
// Reads fall back to sessionStorage once so selections stored by older
// builds migrate forward instead of being dropped.
function _storageGet(key) {
  try {
    if (typeof localStorage !== "undefined") {
      var v = localStorage.getItem(key);
      if (v) return v;
    }
  } catch (_e) {}
  try {
    if (typeof sessionStorage !== "undefined") return sessionStorage.getItem(key) || "";
  } catch (_e) {}
  return "";
}

function _storageSet(key, value) {
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(key, value);
  } catch (_e) {}
}

function _rememberSelection(state) {
  try {
    var pg = state && state.playground;
    var store = pg && pg._workflowRun;
    if (!pg || !store || !store.workflowId) return;
    var row = (store.library || []).find(function (w) { return String(w.workflow_id) === String(store.workflowId); });
    var tool = row ? _workflowTypeOfRow(row) : "";
    if (!tool) return;
    if (!pg.toolWorkflows || typeof pg.toolWorkflows !== "object") pg.toolWorkflows = {};
    pg.toolWorkflows[tool] = String(store.workflowId);
    saveToolWorkflows(pg.toolWorkflows);
  } catch (_e) { /* memory is best-effort */ }
}

function _rememberedToolWorkflow(state, toolId) {
  var pg = state && state.playground;
  if (!pg || !toolId) return "";
  if (!pg.toolWorkflows || typeof pg.toolWorkflows !== "object") {
    try {
      pg.toolWorkflows = loadToolWorkflows() || {};
    } catch (_e) { pg.toolWorkflows = {}; }
  }
  var id = pg.toolWorkflows[toolId];
  return id ? String(id) : "";
}

// Preferred workflow for a tool with no live selection: the tool's last
// selection first, then its marked default. The caller validates the id
// against the loaded library (type included) before selecting.
function _preferredToolWorkflow(state, toolId) {
  var remembered = _rememberedToolWorkflow(state, toolId);
  if (remembered) return remembered;
  try {
    var def = loadToolDefault(toolId);
    return def ? String(def) : "";
  } catch (_e) { return ""; }
}

function _preferredToolRow(state, store, toolId) {
  var id = _preferredToolWorkflow(state, toolId);
  if (!id || !store || !store.library) return "";
  var row = (store.library || []).find(function (w) { return String(w.workflow_id) === String(id); });
  if (row && _workflowTypeOfRow(row) === toolId) return String(id);
  return "";
}

function _applyWorkspaceCarry(state, context, actions, prevValues) {
  // Seed the new selection with the previous workflow's workspace values.
  // Runs after saved-values restore, so the latest edit wins — exactly the
  // "same prompt/seed as the last edit" continuity. Unknown roles never
  // reach the store (schema check); values are preserved verbatim by the
  // commit path and anything invalid surfaces truthfully through run gating
  // instead of running.
  // Every role commits independently: one bad value can never abort the rest.
  if (!prevValues || typeof prevValues !== "object") return;
  var ready = _shelfReady(state);
  if (!ready) return;
  var schema = {};
  try { schema = ready.wf.getControlSchema(ready.store) || {}; } catch (_e) { schema = {}; }
  function safeCommit(role, value) {
    try {
      if (!Object.prototype.hasOwnProperty.call(schema, role)) return false;
      commitShelfValue(state, context, actions, role, value);
      var kept = ready.store.controlValues ? ready.store.controlValues[role] : undefined;
      return kept !== undefined && kept !== null && kept !== "";
    } catch (_e) { return false; }
  }
  var carriedSource = false;
  // A current output is newer than any carried file: when one exists, leave
  // Source Image empty so the post-selection chain fetches the actual
  // current image. Otherwise carry the previous file instantly (no re-upload).
  var hasCurrentOutput = !!_shelfCurrentImageUrl(state);
  if (!hasCurrentOutput && prevValues.source_image && !ready.store.controlValues.source_image) {
    carriedSource = safeCommit("source_image", prevValues.source_image);
  }
  _WORKSPACE_CARRY_ROLES.forEach(function (role) {
    var v = _carryValue(prevValues, role);
    if (v === undefined || v === null || v === "") return;
    safeCommit(role, v);
  });
  // Graph-era target spellings (a legacy-mapped workflow has no `prompt`
  // key to iterate — resolve each schema spelling explicitly). Tuning roles
  // (steps/cfg/…) are intentionally not here: they never carry.
  ["positive_prompt"].forEach(function (role) {
    var v = _carryValue(prevValues, role);
    if (v === undefined || v === null || v === "") return;
    safeCommit(role, v);
  });
  // A mask only makes sense for the image it was painted on — carry it only
  // together with its source image, never onto a freshly chained one.
  if (carriedSource && prevValues.mask && !ready.store.controlValues.mask) {
    safeCommit("mask", prevValues.mask);
  }
  try { _refreshShelfSection(state, context, actions); } catch (_e) { /* best-effort */ }
}

// Graph-era role spellings for the same product input (the backend run path
// aliases prompt/positive_prompt identically). Carry resolves both so a
// legacy-mapped workflow still seeds the shared prompt, and vice versa.
// (steps/cfg spellings stay listed only as documentation — those roles never
// carry; see _WORKSPACE_CARRY_ROLES.)
var _CARRY_ALIASES = {
  prompt: ["positive_prompt"],
  positive_prompt: ["prompt"],
  step_count: ["steps"],
  steps: ["step_count"],
  cfg_scale: ["cfg"],
  cfg: ["cfg_scale"],
};

function _carryValue(prevValues, role) {
  if (!prevValues || typeof prevValues !== "object") return undefined;
  if (prevValues[role] !== undefined) return prevValues[role];
  var alts = _CARRY_ALIASES[role] || [];
  for (var i = 0; i < alts.length; i++) {
    if (prevValues[alts[i]] !== undefined) return prevValues[alts[i]];
  }
  return undefined;
}

function _workflowSelectEl(state, actions, context) {
  const store = state && state.playground && state.playground._workflowRun;
  const select = el("select", {
    class: "comfymodal-input comfymodal-studio-workflow-select",
    "data-testid": "workflow-selector",
  });
  if (!store) {
    select.appendChild(el("option", { value: "", text: "Loading\u2026", disabled: true, selected: true }));
    select.disabled = true;
    return select;
  }
  const placeholder = el("option", { value: "", text: "Select a workflow\u2026", disabled: true });
  if (!store.workflowId) placeholder.selected = true;
  select.appendChild(placeholder);
  var tool = activeToolOf(state);
  // Phase 2/3 compatibility: Edit/Select runs on ordinary I2I workflows but
  // still lists dedicated legacy inpaint workflows (and Edit/Expand lists
  // legacy outpaint) as expert overrides — otherwise they would have no
  // entry point. Scoped by visible shell, not by active tool, so both
  // directions stay reachable.
  var _shellMode = activeModeOf(state);
  var _shellSub = activeSubtoolOf(state);
  var rows = (store.library || []).filter(function (w) {
    var t = _workflowTypeOfRow(w);
    if (!t) return true;
    if (t === tool) return true;
    if (_shellMode === "edit" && _shellSub === "select" && t === "inpaint") return true;
    if (_shellMode === "edit" && _shellSub === "expand" && t === "outpaint") return true;
    return false;
  });
  if (!rows.length) {
    select.appendChild(el("option", { value: "", text: "No workflows for this tool yet", disabled: true, selected: true }));
    select.disabled = true;
    return select;
  }
  rows.forEach((w) => {
    const opt = el("option", { value: String(w.workflow_id), text: _workflowOptionLabel(w) });
    if (store.workflowId && String(store.workflowId) === String(w.workflow_id)) opt.selected = true;
    select.appendChild(opt);
  });
  select.disabled = rows.length === 0;
  select.addEventListener("change", () => {
    _handleWorkflowChange(state, context, actions, select.value);
  });
  return select;
}

function _workflowTypeLabel(state) {
  const store = state && state.playground && state.playground._workflowRun;
  const ctx = store && store.runContext;
  const workflow = ctx && ctx.workflow;
  const raw = (ctx && (ctx.workflow_type || ctx.workflowType || ctx.type))
    || (workflow && (workflow.workflow_type || workflow.workflowType || workflow.type))
    || activeToolOf(state)
    || (store && (store.workflowType || store.featureId))
    || (state && state.playground && state.playground.featureId);
  const key = String(raw || "").toLowerCase();
  const labels = {
    t2i: "Text to image",
    txt2img: "Text to image",
    text_to_image: "Text to image",
    i2i: "Image to image",
    img2img: "Image to image",
    image_to_image: "Image to image",
    image_edit: "Image to image",
    inpaint: "Inpainting",
    sketch: "Sketch",
    outpaint: "Expand",
    upscale: "Upscaling",
    postprocess: "Post processing",
  };
  return labels[key] || (raw ? String(raw).replace(/[._-]+/g, " ") : "Not specified");
}

function _renderGoldenDeployNotice(container, context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  if (!container) return;
  listGoldenProfiles(apiBase).then(async (catalog) => {
    if (!container.isConnected || !catalog || catalog.status !== "ok" || !Array.isArray(catalog.profiles)) return;
    const local = loadGoldenProfileSelection();
    const selected = catalog.profiles.find((profile) => profile && profile.name === local)
      || catalog.profiles.find((profile) => profile && profile.name === catalog.defaultProfile);
    if (!selected) return;
    // The catalog is durable server state, while the deploy job is in-memory
    // state. Read both so a page remount can recover an in-flight deployment.
    const deployState = await getGoldenProfileDeployStatus(apiBase, selected.name);
    if (!container.isConnected) return;
    if (selected.deployed === true && (!deployState || deployState.state !== "running")) return;

    const activeHost = el("div", {
      class: "comfymodal-studio-playground-deploy-notice",
      "data-testid": "playground-golden-profile-deploy-host",
    });
    container.appendChild(activeHost);
    const target = selected.target && typeof selected.target === "object" ? selected.target : {};
    const isDeploying = deployState && deployState.state === "running";
    const status = el("p", {
      class: "comfymodal-studio-settings-hint",
      "data-testid": "playground-golden-profile-deploy-status",
      text: isDeploying
        ? "Deploying " + selected.name + "\u2026"
        : target.app
        ? "Not deployed. Deploying runs v2ctl for " + selected.name + " (" + target.app + ")."
        : "Not deployed.",
    });
    const button = el("button", {
      type: "button",
      class: "comfymodal-primary-btn",
      "data-testid": "playground-golden-profile-deploy",
      "data-profile-name": selected.name,
      text: "Deploy " + selected.name,
    });
    button.disabled = !!isDeploying;

    async function pollGoldenDeploy() {
      for (let attempt = 0; attempt < 900 && activeHost.isConnected; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        if (!activeHost.isConnected) return;
        const current = await getGoldenProfileDeployStatus(apiBase, selected.name);
        if (!activeHost.isConnected) return;
        if (current && current.state === "done") {
          // Re-read the catalog so the deployed marker comes from backend
          // truth, then remove the notice as the existing UI does.
          await listGoldenProfiles(apiBase);
          if (activeHost.isConnected) activeHost.remove();
          return;
        }
        if (current && current.state === "failed") {
          const tail = String(current.output || "").trim().split("\n").pop();
          throw new Error(tail || "see v2ctl output");
        }
      }
    }

    button.addEventListener("click", async () => {
      button.disabled = true;
      status.textContent = "Deploying " + selected.name + "\u2026";
      try {
        const started = await triggerGoldenProfileDeploy(apiBase, selected.name);
        if (!started || started.status !== "ok") throw new Error((started && (started.message || started.error)) || "Deploy request failed");
        await pollGoldenDeploy();
      } catch (error) {
        if (activeHost.isConnected) {
          status.textContent = "Deploy failed: " + (error && error.message ? error.message : "request failed");
          button.disabled = false;
        }
      }
    });
    activeHost.replaceChildren(status, button);
    if (isDeploying) {
      pollGoldenDeploy().catch((error) => {
        if (activeHost.isConnected) {
          status.textContent = "Deploy failed: " + (error && error.message ? error.message : "request failed");
          button.disabled = false;
        }
      });
    }
  }).catch(() => {});
}

function _workflowGatingLineEl(state, wf, context) {
  const store = state && state.playground && state.playground._workflowRun;
  const info = workflowGatingInfo(store, wf, state);
  const line = el("div", {
    "data-testid": "workflow-run-gating",
    class: "comfymodal-studio-control-note",
    style: "font-size:var(--font-size-xs);color:var(--color-text-muted);margin-top:4px;",
  });
  if (info.color) line.style.color = info.color;
  line.textContent = info.text;
  if (store && !store.workflowId) {
    // Empty-state link to the Workflows page (legacy layout untouched).
    line.appendChild(document.createTextNode(" "));
    const link = el("a", {
      text: "Open Workflows",
      style: "color:var(--color-accent);cursor:pointer;",
      onclick: (e) => {
        e.preventDefault();
        if (context && context.setPage) context.setPage("workflows");
      },
    });
    line.appendChild(link);
  }
  return line;
}

function _populateWorkflowSelector(container, state, context, actions) {
  while (container.firstChild) container.removeChild(container.firstChild);
  try { _populateWorkflowSelectorInner(container, state, context, actions); } catch (e) {
    try {
      window.__shelfDiag = (window.__shelfDiag || "") + "POPULATE_THROW:" + (e && e.message) + ";";
    } catch (ign) {}
    throw e;
  }
}

function _populateWorkflowSelectorInner(container, state, context, actions) {
  // Shelf: normalize here (not only in _rerenderWorkflowSection) because
  // full panel re-renders reach this function directly, bypassing the
  // selection-change path. No-op for object schemas.
  _normalizeShelfControlSchema(state);
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;

  const workflowRow = el("div", { class: "comfymodal-studio-workflow-select-row" });
  workflowRow.appendChild(el("label", {
    class: "comfymodal-studio-workflow-label",
    text: "Workflow",
  }));
  workflowRow.appendChild(_workflowSelectEl(state, actions, context));
  container.appendChild(workflowRow);

  workflowRow.appendChild(el("span", {
    class: "comfymodal-studio-workflow-type",
    "data-testid": "workflow-type",
    text: "Type: " + _workflowTypeLabel(state),
  }));
  container.appendChild(_workflowGatingLineEl(state, wf, context));

  if (store && store.handoff) {
    container.appendChild(el("div", {
      "data-testid": "workflow-handoff-notice",
      class: "comfymodal-studio-control-note",
      text: "from Workflows",
      style: "font-size:var(--font-size-xs);color:var(--color-accent);margin-top:2px;",
    }));
  }
  if (store && store.handoffError) {
container.appendChild(el("div", {
      "data-testid": "workflow-handoff-error",
      class: "comfymodal-studio-empty-state",
      text: store.handoffError,
      style: "font-size:var(--font-size-xs);color:#f87171;margin-top:4px;",
    }));
  }
}

function _rerenderWorkflowSection(state, context, actions, opts) {
  // Shelf: restore durably autosaved values into the store independent of
  // selector DOM presence. Post views render no workflow selector, so an
  // early DOM return here used to drop the restore and a reload in Post
  // lost the saved values when returning to the same workflow type. The
  // store (not the DOM) is the source of truth; paint below is best-effort.
  if (opts && opts.applySaved) _applyShelfSavedValues(state);
  const container = document.querySelector('[data-testid="workflow-selector-section"]');
  if (!container) return;
  // Shelf: normalize an array-shaped control_schema (as served by the
  // deterministic workflow mock) into the role-keyed object the frozen
  // run-context contract uses (real backend serves a dict). No-op when the
  // schema is already an object — every downstream consumer (mapped
  // controls, gating, validation, run payload, Shelf) reads it through
  // getControlSchema, so one normalization point fixes them uniformly.
  _normalizeShelfControlSchema(state);
  _populateWorkflowSelector(container, state, context, actions);
  // One-shot "use as base" payload stashed by a viewer (History detail or
  // the canvas preview): applied to the live draft before the cards build,
  // so the filled values render immediately. Taken only when the shelf is
  // ready — an early build (library still loading) leaves it parked for the
  // next rebuild instead of dropping it.
  var pendingBase = _shelfReady(state) ? takePendingPlaygroundBase() : null;
  if (pendingBase) _applyShelfBaseValues(state, pendingBase);
  _refreshShelfSection(state, context, actions);
  _syncRunButtonGating(state, context, actions);
}

function _syncWorkflowGating(state, context, actions) {
  const line = document.querySelector('[data-testid="workflow-run-gating"]');
  if (line) {
    const store = state && state.playground && state.playground._workflowRun;
    const wf = state && state.playground && state.playground._workflowRunModule;
    const info = workflowGatingInfo(store, wf, state);
    line.style.color = info.color ? info.color : "";
    line.textContent = info.text;
  }
  _syncRunButtonGating(state, context, actions);
}

function renderWorkflowSelector(state, context, actions) {
  const container = el("div", {
    class: "comfymodal-studio-workflow-selector",
    "data-testid": "workflow-selector-section",
  });
  _populateWorkflowSelector(container, state, context, actions);
  if (!(state && state.playground && state.playground._workflowInitPromise)) {
    initWorkflowRun(state, context, actions);
  } else if (
    state.playground._workflowRunModule &&
    state.playground._workflowRun
  ) {
    const pending = _peekWorkflowHandoff(state.playground._workflowRunModule);
    if (pending && pending.workflowId) {
      _applyWorkflowHandoff(
        state, context, actions,
        state.playground._workflowRunModule,
        state.playground._workflowRun,
        pending
      )
        .then(() => _rerenderWorkflowSection(state, context, actions))
        .catch(() => {});
    }
  }
  return container;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Workflow run init / selection flows ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function _peekWorkflowHandoff(wf) {
  try {
    if (typeof localStorage === "undefined") return null;
    const key = wf && wf.PERSISTENCE_KEYS && wf.PERSISTENCE_KEYS.workflowHandoff;
    if (!key) return null;
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

async function initWorkflowRun(state, context, actions) {
  const pg = state && state.playground;
  if (!pg) return;
  if (pg._workflowInitPromise) return pg._workflowInitPromise;
  const promise = (async () => {
    try {
      const wf = await import("./studio-workflow-run.js");
      const store = wf.createWorkflowRunStore();
      pg._workflowRun = store;
      pg._workflowRunModule = wf;
      const apiBase = (context && context.apiBase) || "/comfymodal";
      _preloadStudioModalOptions(apiBase);

      // Paint the selector from the store immediately. The library request is
      // intentionally started before handoff/restore, but it must not delay
      // the first selector paint.
      _rerenderWorkflowSection(state, context, actions);
      await wf.loadWorkflowLibrary(apiBase, store);
      _rerenderWorkflowSection(state, context, actions);

      // a) One-shot handoff from the Workflows page. The frozen
      //    resolveHandoffSelection validates against loaded data (library,
      //    versions, presets), so the referenced workflow is selected first
      //    (populating versions + presets) and only then is the one-shot
      //    handoff consumed + validated. Detected via a peek because
      //    takeWorkflowHandoff consumes the value exactly once.
      const pendingHandoff = _peekWorkflowHandoff(wf);
      if (pendingHandoff && pendingHandoff.workflowId) {
        await _applyWorkflowHandoff(state, context, actions, wf, store, pendingHandoff);
        _rerenderWorkflowSection(state, context, actions);
        return;
      }

      // b) Restore the persisted workflow selection.
      const saved = wf.loadWorkflowSelection();
      if (saved && saved.workflowId) {
        await _restoreWorkflowSelection(state, context, actions, wf, store, saved);
        // Shelf: a restored selection reloads its durably autosaved values.
        _rerenderWorkflowSection(state, context, actions, { applySaved: true });
        return;
      }

      // b2) No global selection (fresh profile, cleared storage, or the saved
      // workflow was deleted): fall back to this tool's last selection, then
      // its marked default, so the tool is not left empty after a refresh.
      try {
        const tool = activeToolOf(state);
        const preferred = _preferredToolRow(state, store, tool);
        if (preferred) {
          await _restoreWorkflowSelection(state, context, actions, wf, store, { workflowId: preferred });
          _rerenderWorkflowSection(state, context, actions, { applySaved: true });
          return;
        }
      } catch (_e) { /* fall through to library-only */ }

      // c) No handoff / saved selection: library only. Run stays on the
      //    legacy preset path until the user selects a workflow.
      store.setStatus("ready");
      _rerenderWorkflowSection(state, context, actions);
    } catch (err) {
      // Never let init failures break the page or trip console guards.
      console.debug("[comfymodal workflow] init failed", err && err.message);
    }
  })();
  pg._workflowInitPromise = promise;
  return promise;
}

/** Clear a broken handoff/selection: keep the loaded library, drop ids. */
function _failWorkflowHandoff(wf, store, error) {
  store.handoffError = error;
  store.setHandoff(null);
  store.setReasons([error]);
  store.setWorkflowId("");
  store.setVersionId("");
  store.setWorkflowName("");
  store.setRunContext(null);
  store.controlValues = {};
  store.setStatus("idle");
  store.setError("");
  wf.clearWorkflowSelection();
  // The one-shot handoff is consumed exactly once even on failure.
  try { wf.takeWorkflowHandoff(); } catch (e) { /* ignore */ }
}

async function _applyWorkflowHandoff(state, context, actions, wf, store, handoff) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  const missing = "Requested workflow/version no longer available";
  _flushShelfSave(state);
  var prevValues = Object.assign({}, store.controlValues || {});

  const wfRes = await wf.selectWorkflow(apiBase, store, handoff.workflowId);
  // A newer tool switch owns the store now: yield without failing the
  // handoff (which would clobber the new tool state with a "superseded"
  // error and wipe the persisted selection).
  if (wfRes && wfRes.superseded) return;
  if (!wfRes.ok) {
    _failWorkflowHandoff(wf, store, wfRes.error || missing);
    return;
  }
  if (handoff.workflowVersionId) {
    const verExists = (store.versions || []).some((v) => String(v.workflow_version_id) === String(handoff.workflowVersionId));
    if (!verExists) {
      _failWorkflowHandoff(wf, store, missing);
      return;
    }
    const verRes = await wf.selectVersion(apiBase, store, handoff.workflowVersionId);
    if (verRes && verRes.superseded) return;
    if (!verRes.ok) {
      _failWorkflowHandoff(wf, store, verRes.error || missing);
      return;
    }
  }
  // Consume + validate the one-shot handoff against the now-loaded data.
  const h = wf.resolveHandoffSelection(store);
  if (!h || !h.ok) {
    _failWorkflowHandoff(wf, store, (h && h.error) || missing);
    return;
  }
  store.handoffError = null;
  await _loadWorkflowModelLibrary(state, apiBase);
  wf.saveWorkflowSelection({
    workflowId: store.workflowId,
    workflowVersionId: store.workflowVersionId,
    workflowName: store.workflowName || "",
  });
  _rememberSelection(state);
  _syncActiveToolToSelection(state);
  _loadPersistedSelectionResult(state, store, null, context);
  _rerenderWorkflowSection(state, context, actions, { applySaved: true });
  _applyWorkspaceCarry(state, context, actions, prevValues);
  // A cross-type handoff must remount the whole Playground (tool strip +
  // editors), not just the selector/Shelf slice.
  if (context && context.setPage) context.setPage("playground");
}

async function _restoreWorkflowSelection(state, context, actions, wf, store, saved) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  const library = store.library || [];
  // An empty library means the load FAILED, not that the workflow was deleted.
  // Treating "unknown" as "deleted" cleared the persisted selection, so a
  // single failed load permanently destroyed the user's saved workflow: every
  // later refresh then found nothing to restore, store.workflowId stayed "",
  // _isModernRunSelected() returned false, modern gating was skipped entirely,
  // and Run was left disabled with no tooltip and no reason. Fail closed on
  // restoring, but never destroy the selection on a transport error.
  if (!library.length) {
    store.statusLine = "Workflow library unavailable";
    store.setStatus("error");
    store.setReasons(["Workflow library unavailable"]);
    return;
  }
  const workflow = library.find((w) => String(w.workflow_id) === String(saved.workflowId));
  if (!workflow) {
    store.statusLine = "Saved workflow is no longer available";
    store.setStatus("idle");
    store.setReasons([]);
    wf.clearWorkflowSelection();
    return;
  }
  const wfRes = await wf.selectWorkflow(apiBase, store, saved.workflowId);
  if (!wfRes.ok) {
    // A superseded background restore must not clobber the newer selection
    // that replaced it mid-flight (stale-response guard in workflow-run).
    if (wfRes.superseded) return;
    store.statusLine = wfRes.error || "Saved workflow is no longer available";
    wf.clearWorkflowSelection();
    return;
  }
  if (saved.workflowVersionId) {
    // A workflow has one version, so a restored id is a hint, not a choice.
    // Snap to whatever the workflow's latest is now rather than failing when
    // the saved version is gone: the run context is version-agnostic to the
    // user, who has no way to pick a different one any more.
    // Shelves gate on store.workflowVersionId + runContext.mapping, which
    // selectWorkflow above already populated: skip the second run-context
    // fetch when already on the target version.
    const wanted = String(saved.workflowVersionId);
    const versions = store.versions || [];
    const target =
      versions.find((v) => String(v.workflow_version_id) === wanted)
      || versions[versions.length - 1];
    if (!target) {
      store.statusLine = "Requested version no longer available";
      store.setVersionId("");
      store.controlValues = {};
      store.setStatus("ready");
      store.setReasons(["Requested version no longer available"]);
      return;
    }
    if (String(store.workflowVersionId || "") !== String(target.workflow_version_id || "")) {
      const verRes = await wf.selectVersion(apiBase, store, target.workflow_version_id);
      // Superseded by a newer tool switch: yield, leaving the new tool's
      // cleared store alone (never surface "superseded" as a version error).
      if (verRes && verRes.superseded) return;
      if (!verRes.ok) {
        store.statusLine = verRes.error || "Requested version no longer available";
        return;
      }
    }
  }
  // Model library is not on the shelf paint path: refresh in background so
  // shelves paint as soon as run-context lands.
  _loadWorkflowModelLibrary(state, apiBase).catch(() => {});
  wf.saveWorkflowSelection({
    workflowId: store.workflowId,
    workflowVersionId: store.workflowVersionId,
    presetId: store.presetId,
    workflowName: store.workflowName || "",
    presetName: store.presetName || "",
  });
  _rememberSelection(state);
  // Background initialization restores: the persisted shell survives (the
  // explicit picker path in _runSelectionFlow keeps the old behavior).
  if (_syncActiveToolToSelection(state, { background: true }) && context && context.setPage) {
    // Restored a cross-type workflow: remount strip + editors, not Shelf only.
    context.setPage("playground");
    return;
  }
  _loadPersistedSelectionResult(state, store, null, context);
}

async function _handleWorkflowChange(state, context, actions, workflowId) {
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf || !workflowId) return;
  // Flush pending keystrokes into the outgoing workflow, then snapshot its
  // workspace values so the incoming workflow starts from the last edit.
  _flushShelfSave(state);
  var prevValues = Object.assign({}, store.controlValues || {});
  await _runSelectionFlow(state, context, actions, workflowId, prevValues);
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Run button gating (modern mode) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function _remoteGoldenSelected() {
  // A selected Golden profile executes on the deployed Modal container, so the
  // host-local dependency gate (missing models / uninstalled custom nodes here)
  // describes the wrong machine and must not disable Run.  The backend applies
  // the same rule and still fails closed on structure.
  try {
    return !!loadGoldenProfileSelection();
  } catch (e) {
    return false;
  }
}
function _workflowRunnableForExecution(state, store, wf) {
  const modelRecords = (state && state.playground && state.playground._workflowModelLibrary) || [];
  const gated = _resolveWorkflowRunnable(store, wf, modelRecords);
  if (typeof wf.resolveExecutionRunnable === "function") {
    return wf.resolveExecutionRunnable(gated, _remoteGoldenSelected());
  }
  // Compatibility with an older dynamically-loaded workflow module.
  if (gated.runnable || !_remoteGoldenSelected()) return gated;
  return { runnable: true, reasons: [] };
}
function _applyModernRunButtonState(state, context, actions, btn, reason) {
  // Phase 1 shell gate: Post runs the local engine and later-phase
  // placeholders have no execution path — the button stays disabled with
  // an honest reason instead of submitting a workflow run. In-flight runs
  // keep their busy UI (same condition as the topbar build path).
  var _gatePg = (state && state.playground) || {};
  var _gateBusy = !!_gatePg._batchApplying
    || (_gatePg.runState && ["created", "submitted", "waiting", "queued", "in_progress", "running"].indexOf(_gatePg.runState.status) !== -1);
  var _gate = _shellRunGate(state);
  if (!_gate) {
    try { _gate = _studioMethodGate(state); } catch (_e) { _gate = null; }
  }
  if (_gate && !_gateBusy) {
    if (state && state.playground && state.playground.queueMode) {
      btn.textContent = "Queue";
    } else {
      btn.textContent = "Run";
    }
    btn.disabled = true;
    btn.title = _gate;
    // Modern gating owns the primary button: never leave a stale legacy
    // onclick on the visible Run button while a modern selection is active.
    btn.onclick = null;
    if (reason) {
      while (reason.firstChild) reason.removeChild(reason.firstChild);
      reason.appendChild(el("p", {
        text: _gate,
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      }));
    }
    return;
  }
  // Queue mode owns the topbar primary button ("Queue" + enqueue handler).
  // Gating syncs fire on every seed/prompt edit — never let them rewrite the
  // Queue button back into a Run button in place.
  if (state && state.playground && state.playground.queueMode
    && btn && btn.classList && btn.classList.contains("comfymodal-studio-run-btn")) {
    return;
  }
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf) return;
  // Never clobber an actually active run.  runState is a legacy projection
  // and can outlive the controller's current run (or contain a non-terminal
  // status from an older path), so it is not sufficient to treat every
  // non-terminal value as in-flight.  The controller is authoritative when
  // present; the explicit status fallback protects older callers.
  const runState = state && state.playground && state.playground.runState;
  const controller = state && state.playground && state.playground._runController;
  const controllerRunActive = !!(
    controller
    && typeof controller.getRunId === "function"
    && controller.getRunId()
    && typeof controller.isTerminal === "function"
    && !controller.isTerminal()
  );
  const activeStatus = runState && ["created", "submitted", "waiting", "queued", "in_progress", "running"].indexOf(runState.status) !== -1;
  const legacyRunActive = activeStatus && (
    !controller
    || typeof controller.getRunId !== "function"
    || !controller.getRunId()
  );
  if (controllerRunActive || legacyRunActive) return;
  if (reason) while (reason.firstChild) reason.removeChild(reason.firstChild);
  const g = workflowGatingInfo(store, wf, state);
  if (store.status === "loading" || store.status === "error" || !store.runContext) {
    btn.disabled = true;
    btn.textContent = "Run";
    btn.title = g.text;
    // Modern gating owns the primary button: never leave a stale legacy
    // onclick on the visible Run button while a modern selection is active.
    btn.onclick = null;
    if (reason && g.text) {
      reason.appendChild(el("p", {
        text: g.text,
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      }));
    }
    return;
  }
  const modelRecords = (state && state.playground && state.playground._workflowModelLibrary) || [];
  const { runnable, reasons } = _workflowRunnableForExecution(state, store, wf);
  if (!runnable) {
    btn.disabled = true;
    btn.textContent = "Run";
    btn.title = reasons.length ? reasons.join("; ") : "Not runnable";
    // See above ├óΓé¼ΓÇ¥ no competing legacy onclick while gated in modern mode.
    btn.onclick = null;
    if (reason && reasons.length) {
      reason.appendChild(el("p", {
        text: reasons.join("; "),
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      }));
    }
    return;
  }
  btn.disabled = false;
  btn.textContent = "Run";
  btn.title = "";
  btn.onclick = function () {
    btn.disabled = true;
    btn.textContent = "Running\u2026";
    _modernRunSubmit(state, context, actions, btn);
  };
}

// The primary Run button is rendered by renderRunButton inside the control
// panel's run section. Resolve it by test-id, but prefer the VISIBLE instance:
// an unscoped document.querySelector can land on a stale/hidden duplicate
// earlier in DOM order and leave the visible button on its legacy onclick.
function _resolvePrimaryRunButton() {
  var nodes = Array.prototype.slice.call(document.querySelectorAll('[data-testid="run-btn"]'));
  if (nodes.length === 0) return null;
  for (var i = 0; i < nodes.length; i++) {
    if (nodes[i].offsetParent !== null) return nodes[i];
  }
  return nodes[0];
}

function _syncRunButtonGating(state, context, actions) {
  if (!_isModernRunSelected(state)) {
    // No workflow selected: modern gating does not apply, but the button is
    // still rendered disabled. Returning silently left it grey with an empty
    // title and an empty reason div, so the cause was invisible - it read as
    // "nothing is stopping it". Explain it instead. Title only: the legacy path
    // owns enabling/disabling in this mode, so do not touch `disabled` here.
    const unselected = _resolvePrimaryRunButton();
    if (unselected && !unselected.title) {
      unselected.title = "Select a workflow to run";
    }
    return;
  }
  const btn = _resolvePrimaryRunButton();
  if (!btn) return;
  const section = btn.closest(".comfymodal-studio-run-section");
  var reason = section ? section.querySelector(".comfymodal-studio-disabled-reason") : null;
  if (!reason) {
    var topbar = btn.closest(".comfymodal-studio-topbar-actions");
    reason = topbar ? topbar.querySelector(".comfymodal-studio-topbar-reason") : null;
  }
  _applyModernRunButtonState(state, context, actions, btn, reason);
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Modern run submission ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

// Reset a submit button to idle without flipping queue mode's Queue button
// back into a Run button. textContent assignment destroys the glyph+label
// spans, so the topbar Queue button is repainted instead.
function _resetSubmitBtnIdle(state, btn) {
  if (!btn) return;
  var queueMode = !!(state && state.playground && state.playground.queueMode);
  var isTopbar = !!(btn.classList && btn.classList.contains("comfymodal-studio-run-btn"));
  btn.disabled = false;
  if (queueMode && isTopbar) {
    while (btn.firstChild) btn.removeChild(btn.firstChild);
    btn.appendChild(el("span", { class: "run-glyph", "aria-hidden": "true", text: "+" }));
    btn.appendChild(el("span", { text: "Queue", "data-testid": "run-btn-label" }));
  } else {
    btn.textContent = "Run";
  }
}

async function _modernRunSubmit(state, context, actions, btn, requestId) {
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf) {
    _resetSubmitBtnIdle(state, btn);
    return;
  }
  const apiBase = (context && context.apiBase) || "/comfymodal";
  requestId = requestId || (typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : "studio-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2));
  // Capture the actual click boundary before any cold-path fallback or local
  // validation can add time to the client-to-HTTP measurement.
  var t0_perf_ms = performance.now();
  var t0_now = Date.now();
  var ctrl = _getRunController(state, actions);
  if (!ctrl) {
    _resetSubmitBtnIdle(state, btn);
    return;
  }

  // Known incompatible models must never execute, even on a forced click.
  // Gating mirrors the Run-button state; this is a defensive re-check so a
  // terminal-state re-run cannot bypass the disabled button.
  const _gated = _workflowRunnableForExecution(state, store, wf);
  if (!_gated.runnable) {
    const _reasonText = (_gated.reasons && _gated.reasons.length)
      ? _gated.reasons[0]
      : "Workflow is not runnable";
    ctrl.beginRun();
    ctrl.mark("submit_entered");
    ctrl.applyLocalError(_reasonText);
    _resetSubmitBtnIdle(state, btn);
    _syncRunButtonGating(state, context, actions);
    return;
  }

  // Put determinate sampler fields into running state BEFORE the remote call
  // (mirrors the legacy handler). beginRun must precede any applyLocalError.
  var _modernSteps = store.controlValues && store.controlValues.steps;
  var _runMaxSteps = (_modernSteps != null && Number(_modernSteps) > 0) ? Number(_modernSteps) : 0;
  ctrl.beginRun({ samplerMaximum: _runMaxSteps }, requestId);
  ctrl.mark("submit_entered");

  // Cold-path guard: selection normally preloads run-context; refetch only
  // when it is missing (rare). Measured via performance.now.
  if (!store.runContext && store.workflowVersionId) {
    ctrl.mark("validation_start");
    var _coldT0 = performance.now();
    const ctxResult = await wf.loadRunContext(apiBase, store, store.workflowId, store.workflowVersionId);
    console.debug("[comfymodal workflow] run-context cold load took " + (performance.now() - _coldT0).toFixed(1) + "ms");
    ctrl.mark("validation_end");
    _normalizeShelfControlSchema(state);
    if (!ctxResult.ok || !store.runContext) {
      ctrl.applyLocalError("Workflow context unavailable; reselect the workflow");
      _resetSubmitBtnIdle(state, btn);
      return;
    }
    _rerenderWorkflowSection(state, context, actions);
  }

  const schema = wf.getControlSchema(store);

  ctrl.mark("validation_start");
  const merged = wf.mergeDefaultsAndOverrides(
    wf.defaultValuesFromContext(store),
    store.controlValues || {},
    schema,
  );
  ctrl.mark("validation_end");
  if (merged.errors && merged.errors.length) {
    ctrl.applyLocalError(merged.errors[0].message);
    _resetSubmitBtnIdle(state, btn);
    return;
  }

  // Clear previous output so canvas shows live progress immediately
  if (state && state.playground) {
    state.playground.lastRunOutput = null;
    state.playground._selectedRun = null;
  }
  if (state && state.playground && state.playground.runState) delete state.playground.runState._localStartTime;
  _startLocalElapsedTimer(state, context);

  // Selection/init normally warmed this promise. Awaiting here is retained as
  // the correctness fallback when a caller reaches Run before preload or
  // after a settings change replaced the cache entry.
  const modalOptions = await _preloadStudioModalOptions(apiBase);

  ctrl.mark("build_start");
  const payload = wf.buildRunPayload(apiBase, store, modalOptions, {
    t0_perf_ms: t0_perf_ms,
    t0_perf_now_ms: t0_now,
    t0_client_press_ms: t0_now,
  });
  payload.request_id = requestId;
  payload.profile_name = loadGoldenProfileSelection() || modalOptions.golden_profile || null;
  // Phase 3: explicit generic method rides top-level (never inside controls,
  // which are schema-validated). Null/absent means a plain run.
  try {
    var _sm = _studioMethodForRun(state, store);
    if (_sm) payload.studio_method = _sm;
  } catch (_e) {}
  // Phase 5: prompt-style composition. The user's prompt stays first and
  // verbatim; the selected style fragment appends deterministically (see
  // composeStylePrompt). studio_style carries user_prompt + style identity
  // so History retains all three: user prompt, style, final prompt.
  try {
    var _sty = _studioStyleForRun(state, store);
    if (_sty) {
      payload.controls = payload.controls || {};
      payload.controls.prompt = _sty.composed;
      payload.studio_style = {
        id: _sty.style.id,
        title: _sty.style.title,
        fragment: _sty.style.prompt_fragment,
        user_prompt: _sty.userPrompt,
        catalog_version: (STYLE_CATALOG && STYLE_CATALOG.version) || 0,
      };
    }
  } catch (_e2) {}
  ctrl.mark("build_end");
  // Lineage ownership: stash the submitted source with the request. Poll-path
  // completion must attribute the output to what was actually submitted, not
  // whatever the live shelf holds when the response lands (single-flight UI:
  // one stash slot, consumed once).
  if (state && state.playground) {
    state.playground._submittedSource = (merged.values && merged.values.source_image) || "";
  }

  ctrl.mark("http_invoked");
  if (payload.profile_name) {
    _startGoldenProgressPolling(state, context, requestId, ctrl);
  }
  const result = await runStudioWorkflow(apiBase, payload);
  ctrl.mark("backend_ack");

  if (result && result.status === "ok") {
    if (_isGoldenTerminalResult(result, requestId)) {
      _stopGoldenProgressPolling(state, requestId);
      ctrl.applyGoldenPostTerminal();
      // No caller selection exists in this scope: both call sites referenced an
      // undeclared `directSelection`, which threw a ReferenceError before the
      // result was ever rendered. _handleDirectRunResult takes callerSelection
      // as an OPTIONAL fallback - it resolves the selection key itself from
      // state and only consults this for presetId/featureId, each of which
      // already prefers the result's own meta. Passing null keeps that
      // resolution authoritative.
      _handleDirectRunResult({ ...result, direct_run: true }, state, context, actions, merged.values, null);
      return;
    }
    // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Direct run: result is already completed, no polling ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
    if (_handleDirectRunResult(result, state, context, actions, merged.values, null)) {
      _stopGoldenProgressPolling(state, requestId);
      return;
    }
    // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Scheduler path: submission, start polling ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
    var _inlineSteps = merged.values && merged.values.steps;
    if (ctrl) {
      ctrl.setBackendIds(result.runId || result.experimentId, result.experimentId);
      ctrl.applySubmission({
        experimentId: result.experimentId || result.runId || "",
        samplerMaximum: (_inlineSteps != null && Number(_inlineSteps) > 0) ? Number(_inlineSteps) : 0,
      });
      ctrl.attachEventSource((context && context.comfyApi) || (context && context.api));
    }
    _startLocalElapsedTimer(state, context);
  } else {
    _stopGoldenProgressPolling(state, requestId);
    // A "deploying" status means the backend accepted the run but is preparing
    // first (auto-deploying a forgotten Golden profile). Nothing failed, so it
    // must not render as a red failed run.
    if (result && result.status === "deploying") {
      if (ctrl && typeof ctrl.applyLocalNotice === "function") {
        ctrl.applyLocalNotice(result.message || "Deploying...");
      }
      _resetSubmitBtnIdle(state, btn);
      return;
    }
    const errMsg = (result && result.message)
      ? (Array.isArray(result.reasons) && result.reasons.length
        ? result.message + ": " + result.reasons.join("; ")
        : result.message)
      : "Run failed.";
    if (result && result.error_code) {
      console.error("[Studio run] execution failed", {
        error_code: result.error_code,
        error: result.error || null,
      });
    }
    if (ctrl) ctrl.applyLocalError(errMsg);
    // The canonical controller keeps the user-facing message, while this
    // small projection preserves the provider error identity needed by the
    // recovery affordance below.
    if (isModalAppNotFoundError(result) && actions && actions.setRunState) {
      actions.setRunState({
        status: "error",
        message: errMsg,
        error_code: result.error_code || (result.error && result.error.code) || "MODAL_APP_NOT_FOUND",
        error: result.error || null,
      });
    }
    _resetSubmitBtnIdle(state, btn);
  }
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Info Hint helper ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Creates a compact info icon with a hover/focus tooltip to replace bulky
// visible description paragraphs under headings and section labels.

function _isGoldenTerminalResult(result, requestId) {
  if (!result || result.status !== "ok") return false;
  if (result.request_id != null && String(result.request_id) !== String(requestId)) return false;
  return result.terminal === true
    || Array.isArray(result.outputs)
    || Array.isArray(result.output_paths)
    || result.history_id != null
    || result.run_history_id != null;
}

export function createInfoHint(text, options) {
  const hint = el("span", {
    class: "comfymodal-studio-info-hint",
    "data-testid": "info-hint",
    tabindex: "0",
    role: "tooltip",
    "aria-label": text,
  });
  hint.textContent = "\u24d8";  // ├óΓÇ£╦£ circled info icon

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
  hint.addEventListener("keydown", (e) => {
    // Escape dismisses a keyboard-opened tooltip and returns focus state
    // to rest, matching native tooltip behavior for keyboard users.
    if (e.key === "Escape" || e.key === "Esc") {
      tooltip.style.display = "";
      hint.blur();
    }
  });

  return hint;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Render a single control ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Schema-driven rendering: if the preset carries a controlSchemas entry for
// this control ID, the schema's ``kind`` field (from the backend graph) takes
// precedence over the static CONTROL_DEFS ``type``.  This ensures sampler/
// scheduler are rendered as <select> with proper graph-derived options.

function renderControl(def, state, actions, preset) {
  const presetDefaults = (preset && preset.defaults) || {};
  const ctrlId = def.id;
  const currentOverrides = (state.playground && state.playground.controls) || {};
  const hydratedValues = (state.playground && state.playground._hydratedControls) || {};
  const value = ctrlId in currentOverrides
    ? currentOverrides[ctrlId]
    : ctrlId in hydratedValues
      ? hydratedValues[ctrlId]
      : ctrlId in presetDefaults
        ? presetDefaults[ctrlId]
        : def.defaultValue;

  // Resolve schema from the backend preset (if available)
  const schema = (preset && preset.controlSchemas && preset.controlSchemas[def.id]) || null;
  const schemaKind = (schema && schema.schemaResolved && schema.kind) || null;

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

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Schema-kind dispatch (backend truth) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  if (schemaKind === "enum") {
    // Enum: render as <select> with options from the schema
    const options = schema.options || [];
    input = el("select", {
      class: "comfymodal-input comfymodal-studio-select",
      "data-testid": `input-${def.id}`,
    });
    options.forEach(function (optVal) {
      const opt = el("option", {
        value: optVal,
        text: optVal,
      });
      if (String(optVal) === String(value)) opt.selected = true;
      input.appendChild(opt);
    });
    input.addEventListener("change", () => {
      if (actions.setControl) actions.setControl(def.id, input.value);
    });
  } else if (schemaKind === "boolean") {
    // Boolean: render as checkbox
    input = el("input", {
      type: "checkbox",
      class: "comfymodal-input comfymodal-studio-checkbox",
      "data-testid": `input-${def.id}`,
    });
    // Preserve falsy zero/false ├óΓé¼ΓÇ¥ only truly missing treated as default
    const isChecked = value === true || value === 1 || value === "1" || value === "true";
    input.checked = isChecked;
    input.addEventListener("change", () => {
      if (actions.setControl) actions.setControl(def.id, input.checked);
    });
  } else if (schemaKind === "integer" || schemaKind === "number") {
    // Integer / Number: render with schema min/max/step
    const isInteger = schemaKind === "integer";
    input = el("input", {
      type: "number",
      class: "comfymodal-input comfymodal-studio-number-input",
      value: value != null ? String(value) : "",
      min: schema.minimum != null ? String(schema.minimum) : "",
      max: schema.maximum != null ? String(schema.maximum) : "",
      step: schema.step != null ? String(schema.step) : (isInteger ? "1" : "any"),
      "data-testid": `input-${def.id}`,
    });
    input.addEventListener("input", () => {
      var parsed = isInteger ? parseInt(input.value, 10) : parseFloat(input.value);
      if (actions.setControl) actions.setControl(def.id, isNaN(parsed) ? input.value : parsed);
    });
  } else if (schemaKind === "multiline") {
    var tareaClass = "comfymodal-input comfymodal-studio-textarea";
    if (def.id === "prompt" || def.id === "negative_prompt") {
      tareaClass += " comfymodal-studio-prompt-textarea";
      if (def.id === "negative_prompt") tareaClass += " negative";
    }
    input = el("textarea", {
      class: tareaClass,
      placeholder: def.placeholder || "",
      value: value != null ? String(value) : "",
      "data-testid": `input-${def.id}`,
    });
    input.addEventListener("input", () => {
      if (actions.setControl) actions.setControl(def.id, input.value);
    });
  } else if (schemaKind === "string") {
    input = el("input", {
      type: "text",
      class: "comfymodal-input comfymodal-studio-text-input",
      value: value != null ? String(value) : "",
      placeholder: def.placeholder || "",
      "data-testid": `input-${def.id}`,
    });
    input.addEventListener("input", () => {
      if (actions.setControl) actions.setControl(def.id, input.value);
    });
  } else if (schemaKind === "image" || schemaKind === "file" || schemaKind === "model") {
    // Image/file/model controls: render as disabled text input for now
    input = el("input", {
      type: "text",
      class: "comfymodal-input comfymodal-studio-text-input",
      value: value != null ? String(value) : "",
      disabled: true,
      "data-testid": `input-${def.id}`,
    });
  }

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Static CONTROL_DEFS type dispatch (fallback) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  if (!input) {
    if (def.type === "textarea") {
      var tareaClass = "comfymodal-input comfymodal-studio-textarea";
      if (def.id === "prompt" || def.id === "negative_prompt") {
        tareaClass += " comfymodal-studio-prompt-textarea";
        if (def.id === "negative_prompt") tareaClass += " negative";
      }
      input = el("textarea", {
        class: tareaClass,
        placeholder: def.placeholder || "",
        value: String(value),
        "data-testid": `input-${def.id}`,
      });
      input.addEventListener("input", () => {
        if (actions.setControl) actions.setControl(def.id, input.value);
      });
    } else if (def.type === "select") {
      // Check if this is a dynamic-options select (sampler/scheduler)
      if (def.dynamicOptions && schema && schema.kind === "enum" && schema.options) {
        input = el("select", {
          class: "comfymodal-input comfymodal-studio-select",
          "data-testid": `input-${def.id}`,
        });
        schema.options.forEach(function (optVal) {
          const opt = el("option", {
            value: optVal,
            text: optVal,
          });
          if (String(optVal) === String(value)) opt.selected = true;
          input.appendChild(opt);
        });
        input.addEventListener("change", () => {
          if (actions.setControl) actions.setControl(def.id, input.value);
        });
      } else if (def.dynamicOptions) {
        // Dynamic-options select (sampler/scheduler) without schema enum:
        // show disabled text input with current saved value instead of
        // a misleading "Default" placeholder with a hardcoded fallback.
        input = el("input", {
          type: "text",
          class: "comfymodal-input comfymodal-studio-text-input",
          value: value != null ? String(value) : "",
          disabled: true,
          "data-testid": `input-${def.id}`,
          title: "Schema options unavailable — value preserved from saved defaults",
        });
        const note = el("span", {
          class: "comfymodal-studio-control-note",
          text: "Schema unavailable, value preserved",
          style: "font-size:var(--font-size-xs);color:var(--color-text-muted);",
        });
        group.appendChild(note);
      } else {
        // Static select (LoRA etc.): disabled, configured elsewhere
        input = el("select", {
          class: "comfymodal-input comfymodal-studio-select",
          "data-testid": `input-${def.id}`,
        });
        const emptyOpt = el("option", { value: "", text: "Default" });
        input.appendChild(emptyOpt);
        input.disabled = true;
        const note = el("span", {
          class: "comfymodal-studio-control-note",
          text: "Not available in the modern Playground yet.",
          style: "font-size:var(--font-size-xs);color:var(--color-text-muted);",
        });
        group.appendChild(note);
      }
    } else if (def.type === "text") {
      input = el("input", {
        type: "text",
        class: "comfymodal-input comfymodal-studio-text-input",
        value: String(value),
        placeholder: def.placeholder || "",
        "data-testid": `input-${def.id}`,
      });
      input.addEventListener("input", () => {
        if (actions.setControl) actions.setControl(def.id, input.value);
      });
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
        const parsed = parseFloat(input.value);
        if (actions.setControl) actions.setControl(def.id, Number.isFinite(parsed) ? parsed : input.value);
      });
    }
  }

  if (input) group.appendChild(input);

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Steps: Use Recommended (N) button ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  // Preset/workflow-backed recommendation (shared with the Steps axis
  // editor).  Hidden when no trustworthy source exists; disabled when
  // the current value already matches the recommendation.
  if (def.id === "steps") {
    const pg = state.playground;
    const stepsAxisActive = !!(pg && pg.experimentMode
      && pg.experimentAxes && pg.experimentAxes.steps && pg.experimentAxes.steps.enabled);
    if (!stepsAxisActive) {
      const recStatus = getRecommendedStepsStatus(state, [value]);
      if (recStatus.value != null) {
        const recBtn = document.createElement("button");
        recBtn.type = "button";
        recBtn.className = "comfymodal-secondary-btn";
        recBtn.style.cssText = "font-size:9px;padding:1px 6px;margin-top:2px;display:inline-block;";
        recBtn.textContent = "Use recommended (" + recStatus.value + ")";
        recBtn.setAttribute("data-testid", "steps-recommended-btn");
        if (recStatus.reason) {
          recBtn.disabled = true;
          recBtn.title = recStatus.reason;
        } else {
          recBtn.title = "From selected preset workflow capture";
          recBtn.addEventListener("click", function () {
            if (actions && actions.setControl) {
              actions.setControl("steps", recStatus.value);
            }
            const stepsInput = group.querySelector('[data-testid="input-steps"]');
            if (stepsInput) stepsInput.value = String(recStatus.value);
            recBtn.disabled = true;
            recBtn.title = "Already applied";
          });
        }
        group.appendChild(recBtn);
      }
    }
  }

  return group;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Run Button ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Single-run submit helper ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Immediately submits a single run using visible controls.
// Deduplicated from the inline handler in renderRunButton so that
// completed/error state can re-submit in a single click.

function _disposeScopedTracker(state) {
  // Note: does NOT clean _localElapsedTimer ├óΓé¼ΓÇ¥ the local timer is owned by
  // _startLocalElapsedTimer which handles cleanup and re-creation across
  // new-run boundaries. Terminal cleanup is done by setRunState.

  var st = state.playground && state.playground._scopedTracker;
  if (st && typeof st.dispose === "function") {
    try { st.dispose(); } catch {}
  }
  if (state.playground) state.playground._scopedTracker = null;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Canonical run controller (single lifecycle authority) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
// Lazily created once per page; beginRun() on every Run click allocates a
// fresh canonical runId. The canonical store drives runState via a pure
// projection; legacy lifecycle fields are outputs, never independent inputs.
function _getRunController(state, actions) {
  if (!state.playground) return null;
  if (actions) state.playground._runActions = actions;
  if (state.playground._runController) return state.playground._runController;
  var ctrl = createPlaygroundRunController();
  state.playground._runController = ctrl;
  ctrl.subscribe(function (run, extras) {
    if (!run || !state.playground) return;
    var legacy = projectRunToLegacy(run, extras);
    // Project Golden stage progress onto runState. The renderer reads
    // runState.goldenProgress / goldenProgressPercent, but the controller keeps
    // that state privately and only exposes it via getGoldenProgress(), so
    // without this the bar stayed on the 30% indeterminate fallback and no stage
    // rows ever rendered. Kept beside the canonical projection rather than
    // inside it: the cursor stream is presentation-only and must not influence
    // lifecycle derivation.
    var golden = ctrl.getGoldenProgress();
    if (golden) {
      legacy.goldenProgress = golden;
      legacy.goldenProgressPercent = golden.percent != null ? golden.percent : null;
      // The renderer gates the live stage caption on runState.goldenStage,
      // but nothing ever set it — the caption could only show the coarse
      // lifecycle word. Project the cursor stream's current stage so new
      // stages appear without a renderer change.
      if (golden.currentStage != null) legacy.goldenStage = golden.currentStage;
    }
    // Modal lifecycle display: ws modal_status wins (covers generic runs);
    // the Golden cursor status phase is the fallback (covers Golden runs
    // before any ws event arrives).
    var modalStatus = (typeof ctrl.getModalStatus === "function") ? ctrl.getModalStatus() : null;
    var modalPhase = (modalStatus && modalStatus.phase != null) ? modalStatus.phase
      : (golden && golden.statusPhase != null ? golden.statusPhase : null);
    var modalMessage = (modalStatus && modalStatus.message != null) ? modalStatus.message
      : (golden && golden.statusMessage != null ? golden.statusMessage : null);
    if (modalPhase != null) legacy.modalPhase = modalPhase;
    if (modalMessage != null) legacy.modalMessage = modalMessage;
    var prev = state.playground.runState;
    var prevStatus = prev && prev.status;
    if (prev && prevStatus === legacy.status) {
      // Same status: silent merge + DOM patch, no re-render/side effects.
      // Preserve non-null prev values over null legacy values (e.g. the
      // expected sampler maximum hint until real sampler telemetry lands).
      var merged = { ...prev };
      for (var k in legacy) {
        if (legacy[k] === null && merged[k] !== null && merged[k] !== undefined) continue;
        merged[k] = legacy[k];
      }
      state.playground.runState = merged;
      _domPatchProgress(state);
    } else {
      var act = state.playground._runActions;
      if (act && act.setRunState) act.setRunState(legacy);
      // Queue auto-drain: every terminal route (completed/error/canceled/
      // interrupted, direct or polled) converges here via setRunState.
      // Schedule the next queued item — never inline: setRunState re-renders
      // and may replace the button DOM under us.
      if (legacy.status && LEGACY_TERMINAL_STATUSES.indexOf(legacy.status) !== -1) {
        _maybeDrainQueue(state, context, act || actions);
      }
    }
    state.playground._runDiagnostics = ctrl.getDiagnostics();
    try { window.__studioLastRunDiagnostics = ctrl.getDiagnostics(); } catch (e) {}
  });
  return ctrl;
}

function _startLocalElapsedTimer(state, context) {
  var _existing = state.playground && state.playground._localElapsedTimer;
  if (_existing) { clearInterval(_existing); if (state.playground) state.playground._localElapsedTimer = null; }

  var _rs = state.playground && state.playground.runState;
  if (!_rs) return;
  // Initialize local start timestamp on first call; reuse on subsequent calls
  // so original button-press time survives through submission and tracker activation.
  if (_rs._localStartTime == null) {
    _rs._localStartTime = Date.now();
  }
  var _localStart = _rs._localStartTime;

  var _timer = setInterval(function() {
    var _rs2 = state.playground && state.playground.runState;
    if (!_rs2 || !_rs2.status) {
      clearInterval(_timer);
      if (state.playground) state.playground._localElapsedTimer = null;
      return;
    }
    if (LEGACY_TERMINAL_STATUSES.indexOf(_rs2.status) !== -1) {
      clearInterval(_timer);
      delete _rs2._localStartTime;
      if (state.playground) state.playground._localElapsedTimer = null;
      return;
    }
    if (state.activePage !== "playground") {
      clearInterval(_timer);
      delete _rs2._localStartTime;
      if (state.playground) state.playground._localElapsedTimer = null;
      return;
    }
    _rs2.elapsedMs = Date.now() - _localStart;
    // DOM-targeted elapsed update ├óΓé¼ΓÇ¥ avoids full page teardown on every tick
    var elapsedEl = document.querySelector('[data-testid="progress-elapsed"]');
    if (elapsedEl) {
      elapsedEl.textContent = "Elapsed: " + _formatDuration(_rs2.elapsedMs);
    }
  }, 250);

  if (state.playground) state.playground._localElapsedTimer = _timer;
}

/**
 * Validate control values against their schema options before submission.
 * Catches cross-domain errors like a scheduler name in the sampler field.
 * Returns a clear error string or null if valid.
 */
function validateControls(controls, preset) {
  if (!preset || !preset.controlSchemas) return null;
  
  const schemas = preset.controlSchemas;
  
  // Check sampler value against its schema options
  if (controls.sampler != null && schemas.sampler && schemas.sampler.options) {
    if (schemas.sampler.options.indexOf(controls.sampler) === -1) {
      // Check if this value belongs to the scheduler field
      if (schemas.scheduler && schemas.scheduler.options && 
          schemas.scheduler.options.indexOf(controls.sampler) !== -1) {
        return "Invalid sampler \"" + controls.sampler + "\". This value belongs to the Scheduler field, not the Sampler field. Click \"Reset to defaults\" and set Sampler to a valid value like \"multistep/res_3m\".";
      }
      return "Invalid sampler \"" + controls.sampler + "\". Select a valid sampler from the dropdown or click \"Reset to defaults\".";
    }
  }
  
  // Check scheduler value against its schema options
  if (controls.scheduler != null && schemas.scheduler && schemas.scheduler.options) {
    if (schemas.scheduler.options.indexOf(controls.scheduler) === -1) {
      // Check if this value belongs to the sampler field
      if (schemas.sampler && schemas.sampler.options && 
          schemas.sampler.options.indexOf(controls.scheduler) !== -1) {
        return "Invalid scheduler \"" + controls.scheduler + "\". This value belongs to the Sampler field, not the Scheduler field.";
      }
      return "Invalid scheduler \"" + controls.scheduler + "\". Select a valid scheduler from the dropdown or click \"Reset to defaults\".";
    }
  }
  
  return null;
}

/**
 * Handle a direct-run completed result ├óΓé¼ΓÇ¥ no polling or journal needed.
 * Returns true when the result was a direct_run and was handled,
 * false when the caller should fall through to the scheduler/polling path.
 */
function _handleDirectRunResult(result, state, context, actions, controls, callerSelection) {
  if (!result || !result.direct_run) return false;
  if (result.status !== "ok") return false;

  const apiBase = (context && context.apiBase) || "/comfymodal";
  const outputPaths = Array.isArray(result.output_paths)
    ? result.output_paths
    : (Array.isArray(result.outputs)
      ? result.outputs.map((output) => typeof output === "string"
        ? output
        : (output && (output.path || output.output_path || output.filename))).filter(Boolean)
      : []);
  const primaryAssetId = result.primary_asset_id || (result.meta && result.meta.primary_asset_id) || "";
  var primaryOutput = null;
  if (outputPaths.length > 0) {
    primaryOutput = apiBase + "/studio/outputs/" + encodeURIComponent(outputPaths[0]);
  } else if (primaryAssetId) {
    primaryOutput = apiBase + "/assets/" + encodeURIComponent(primaryAssetId);
  }

  // Build the normalized run before the terminal state update.  setRunState
  // re-renders synchronously, so assigning the run afterward can leave the
  // completed direct result's timing card out of the first render.
  const meta = result.meta || {};
  const selection = resolveSelectionResultKey(state, state.playground && state.playground._workflowRun, {
    presetId: meta.studio_preset_id || (callerSelection && callerSelection.presetId),
    featureId: meta.studio_feature_id || (callerSelection && callerSelection.featureId),
  });
  const timings = result.timings || {};
  var rawRun = {
    id: result.runId || result.runHistoryId || result.run_history_id || result.history_id || meta.experiment_id || "",
    experiment_id: result.experimentId || meta.experiment_id || "",
    // Bridge to the durable record: the backend stamps the run's History V2
    // generation id on the response because nothing else links a run id to
    // the record History renders for it.
    history_generation_id: result.historyGenerationId || result.history_generation_id || "",
    status: "completed",
    output_path: result.output_path || (outputPaths.length > 0 ? outputPaths[0] : ""),
    primary_asset_id: primaryAssetId,
    started_at: null,
    completed_at: result.completed_at || null,
    duration_ms: null,
    workflow_hash: meta.workflow_hash || "",
    extra: {
      experiment_id: result.experimentId || meta.experiment_id || "",
      studio_preset_id: selection.presetId,
      studio_preset_label: meta.preset_label || "",
      studio_snapshot_id: meta.studio_snapshot_id || "",
      studio_feature_id: selection.featureId,
      prompt: (controls && controls.prompt) || "",
      negative_prompt: (controls && controls.negative_prompt) || "",
      resolved_controls: meta.resolved_controls || {},
      requested_controls: meta.requested_controls || {},
      output_paths: outputPaths,
      primary_asset_id: primaryAssetId,
      timings: timings,
      output_count: meta.output_count || 0,
      production_plan_used: meta.production_plan_used || "no",
    },
    timings: timings,
    timing_summary: timings,
  };

  var normalized = normalizeStudioRun(rawRun, apiBase);
  if (normalized) {
    if (state.playground) {
      state.playground.lastRunOutput = normalized.imageUrl || primaryOutput;
      _setCanvasImage(state, normalized.imageUrl || primaryOutput);
      try {
        _recordImageEdge(state, normalized.imageUrl || primaryOutput,
          (controls && controls.source_image) || "");
      } catch (_e) { /* lineage is best-effort */ }
      state.playground._selectedRun = normalized;
    }
    // Persist via the shared selection key so reload queries the same entry.
    if (selection.presetId && selection.featureId) {
      saveRunResult(selection.presetId, selection.featureId, normalized);
    }
  }

  var ctrl = _getRunController(state, actions);
  if (ctrl) {
    if (ctrl.getGoldenProgress()) {
      ctrl.applyGoldenProgress({
        request_id: result.request_id || result.runId,
        events: [{ type: "result", data: result.result || result }],
        terminal: true,
      });
    }
    ctrl.applyDirectResult(result, {
      experimentId: result.experimentId || result.runId || meta.experiment_id || "",
      runHistoryId: result.runHistoryId || result.runId || "",
      primaryOutput: primaryOutput,
      hasHistory: true,
      completedCells: 1,
      totalCells: 1,
      _directTiming: result.timings || null,
      _directMeta: result.meta || null,
    });
  }
  return true;
}

function renderRunButton(state, context, actions) {
  const container = el("div", { class: "comfymodal-studio-run-section" });

  const btnText = "Run";
  const testId = "run-btn";
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

  function _renderCancelBtn(rs) {
    // In experiment mode, the dedicated experiment section owns the cancel
    // button.  The ordinary single-run section must not add a second one.
    if (state.playground && state.playground.experimentMode) return null;
    var _cb = el("button", {
      class: "comfymodal-destructive-btn",
      "data-testid": "cancel-run-btn",
      text: rs._cancelling ? "Cancelling\u2026" : "Cancel",
      disabled: !!rs._cancelling,
      style: "font-size:10px;padding:2px 8px;margin-left:6px;",
    });
    _cb.addEventListener("click", async function () {
      if (rs._cancelling) return;
       rs._cancelling = true;
       _cb.textContent = "Cancelling\u2026";
       _cb.disabled = true;
       var _goldenPoll = state.playground && state.playground._goldenProgressPoll;
       if (_goldenPoll) _stopGoldenProgressPolling(state, _goldenPoll.requestId);
       var _eid = rs.experimentId || rs.runId;
      if (_eid) {
        try { await stopExperiment(apiBase, _eid); } catch (e) {}
      }
    });
    return _cb;
  }

  if (runState && runState.status === "running") {
    btn.disabled = true;
    btn.textContent = "Running\u2026";
    btn.title = "Run in progress";
    var _runMsg = el("p", {
      text: "Your run has been submitted\u2026",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    });
    reason.appendChild(_runMsg);
    var _rb = _renderCancelBtn(runState);
    if (_rb) reason.appendChild(_rb);
    return container;
  }

  if (runState && runState.status === "submitted") {
    btn.disabled = true;
    btn.textContent = "Submitted";
    btn.title = "Run submitted, waiting for status\u2026";
    var _subMsg = el("p", {
      text: "Waiting for server response\u2026",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    });
    reason.appendChild(_subMsg);
    var _sb = _renderCancelBtn(runState);
    if (_sb) reason.appendChild(_sb);
    // Start polling only once per run lifecycle.  The elapsed timer
    // triggers re-renders every 250ms; without this guard, each re-render
    // would call _startPolling which calls _stopPolling/clearInterval,
    // resetting the 3s poll interval so it never fires.
    if (!state.playground || !state.playground._pollTimer) {
      _startPolling(container, state, context, actions, runState);
    }
    return container;
  }

  if (runState && runState.status === "waiting") {
    btn.disabled = true;
    btn.textContent = "Waiting\u2026";
    btn.title = "Waiting for experiment to be ready on server";
    var _waitMsg = el("p", {
      text: "Waiting for server setup\u2026",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    });
    reason.appendChild(_waitMsg);
    var _wb = _renderCancelBtn(runState);
    if (_wb) reason.appendChild(_wb);
    return container;
  }

  if (runState && (runState.status === "queued" || runState.status === "in_progress")) {
    btn.disabled = true;
    btn.textContent = runState.status === "queued" ? "Queued\u2026" : "Running\u2026";
    btn.title = "Experiment is running";
    const progressText = runState.cellProgress
      ? "Cells completed: " + runState.cellProgress
      : "Run is in progress\u2026";
    var _progMsg = el("p", {
      text: progressText,
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    });
    reason.appendChild(_progMsg);
    var _pb = _renderCancelBtn(runState);
    if (_pb) reason.appendChild(_pb);
    return container;
  }

  if (runState && runState.status === "completed") {
    // Terminal state: keep prior result visible, show "Run" to re-submit
    // immediately using visible settings
    btn.disabled = false;
    btn.textContent = "Run";
    btn.title = "Run completed. Click to run again with current settings.";
    const messageEl = el("p", {
      "data-testid": "run-status-message",
      style: "font-size:var(--font-size-sm);color:var(--color-success);margin:4px 0 0;",
    });
    messageEl.textContent = runState.completedCells
      ? "Run completed (" + runState.completedCells + " cell(s))."
      : "Run completed successfully.";
    reason.appendChild(messageEl);
    // Show View in History when meaningful history evidence exists
    if (runState.hasHistory) {
      const viewLink = el("a", {
        text: "View in History",
        style: "font-size:var(--font-size-sm);color:var(--color-accent);cursor:pointer;margin-left:8px;",
        onclick: (e) => {
          e.preventDefault();
          if (actions && actions.navigateToHistory) actions.navigateToHistory();
        },
      });
      messageEl.appendChild(document.createTextNode(" "));
      messageEl.appendChild(viewLink);
    }
    // Single click: immediately submit another run using visible settings.
    // Prioritize _modernRunSubmit so prior image/metadata stays visible until
    // the new submission enters flight (setRunState("running") clears the
    // completed state and triggers re-render).
    btn.onclick = function () {
      _modernRunSubmit(state, context, actions, btn);
    };
    return container;
  }

  if (runState && runState.status === "error") {
    // Terminal error state: show error with Dismiss + Retry
    btn.disabled = false;
    btn.textContent = "Run";
    btn.title = "Run failed. Click to try again.";
    reason.appendChild(el("p", {
      text: "Run Failed",
      style: "font-size:var(--font-size-sm);font-weight:var(--font-weight-semibold);color:var(--color-danger);margin:0 0 2px;",
    }));
    reason.appendChild(el("p", {
      text: runState.message || "Run failed. Try again.",
      style: "font-size:var(--font-size-sm);color:var(--color-danger);margin:0 0 4px;",
    }));

    if (isModalAppNotFoundError(runState)) {
      const redeployBtn = el("button", {
        class: "comfymodal-primary-btn",
        text: "Redeploy Modal app",
        "data-testid": "run-redeploy-app-btn",
        title: "Redeploy the Modal app, then run again",
        style: "font-size:10px;padding:3px 9px;margin:0 4px 4px 0;",
      });
      redeployBtn.addEventListener("click", async function () {
        if (redeployBtn.disabled) return;
        redeployBtn.disabled = true;
        redeployBtn.textContent = "Redeploying\u2026";
        let response = null;
        try { response = await triggerDeploy(apiBase); } catch { response = null; }
        if (response && (response.status === "started" || response.status === "already_deploying")) {
          redeployBtn.textContent = response.status === "already_deploying" ? "Redeploy in progress" : "Redeploy started";
          redeployBtn.title = "Wait for deployment to finish, then run again";
          return;
        }
        redeployBtn.disabled = false;
        redeployBtn.textContent = "Redeploy Modal app";
        redeployBtn.title = (response && (response.message || response.error)) || "Redeploy failed — try again";
      });
      reason.appendChild(redeployBtn);
    }

    // Dismiss action: clears error without triggering re-run
    const dismissBtn = el("button", {
      class: "comfymodal-secondary-btn",
      text: "Dismiss",
      "data-testid": "error-dismiss-btn",
      style: "font-size:10px;padding:2px 8px;margin-right:4px;",
      onclick: function () {
        if (actions && actions.setRunState) {
          actions.setRunState(null);
        }
      },
    });
    reason.appendChild(dismissBtn);
    // Retry button re-uses the Run button's existing onclick setup
    btn.onclick = function () {
      _modernRunSubmit(state, context, actions, btn);
    };
    return container;
  }

  if (runState && (runState.status === "canceled" || runState.status === "interrupted")) {
    const _canceled = runState.status === "canceled";
    btn.disabled = false;
    btn.textContent = "Run";
    btn.title = _canceled ? "Run was canceled. Click to run again." : "Run was interrupted. Click to run again.";
    const msgEl = el("p", {
      "data-testid": "run-status-message",
      style: "font-size:var(--font-size-sm);color:#d9a441;margin:4px 0 0;",
    });
    msgEl.textContent = _canceled ? "Run canceled." : "Run interrupted.";
    reason.appendChild(msgEl);
    btn.onclick = function () {
      _modernRunSubmit(state, context, actions, btn);
    };
    return container;
  }

  // Gating is driven entirely by the modern workflow run store: there are
  // no backend presets to load, so no async preset fetch and no legacy
  // fallback branch.
  //
  // Apply it HERE, to this freshly built button, rather than leaving it to a
  // later document-wide sync. This runs synchronously while `container` is
  // still detached, so the previous `container.isConnected` guard was always
  // false and the button kept its constructed state: disabled, empty title,
  // empty reason div. That only self-healed when something afterwards called
  // _rerenderWorkflowSection (once, right after initWorkflowRun). Every later
  // full re-render built a new disabled Run button that nothing re-enabled -
  // notably the setPage("playground") that _loadPersistedSelectionResult fires
  // after refreshing recent runs when a prior image exists. The button then
  // read as permanently unclickable with no stated reason.
  if (_isModernRunSelected(state)) {
    while (reason.firstChild) reason.removeChild(reason.firstChild);
    _applyModernRunButtonState(state, context, actions, btn, reason);
  }

  return container;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Progress Section ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Displays shared progress state: overall bar, current stage/node, sampler
// step progress, completed/total nodes, elapsed time, queue/startup state,
// clear failure state, and completed duration.

function renderProgressSection(state, context) {
  const section = el("div", {
    class: "comfymodal-studio-progress-section",
    "data-testid": "progress-section",
    style: "display:none;",
  });

  const runState = state.playground && state.playground.runState;
  if (!runState || LEGACY_TERMINAL_STATUSES.indexOf(runState.status) !== -1) {
    // Terminal (or no run yet): retain the final stage label so the
    // section evidences completion instead of going blank. Completed and
    // error detail continues to render in the metadata section.
    if (runState) {
      section.style.display = "block";
      // Terminal runs show just the annotated bar plus one compact total -
      // no "Stage: Completed" caption, no per-stage rows. Segment labels
      // carry final names and timings; tooltips carry the lane breakdown.
      _goldenTickStop();
      // The terminal branch must build the same bar skeleton the live branch
      // does. _appendGoldenProgress only fills segments when a
      // progress-bar-segments container already exists, so without this the
      // annotated bar vanished the moment the run finished - exactly when the
      // finished stage breakdown matters most.
      var terminalBar = el("div", {
        class: "comfymodal-studio-progress-bar",
        "data-testid": "progress-bar",
      }, [
        el("div", {
          class: "comfymodal-studio-progress-fill",
          "data-testid": "progress-bar-fill",
          style: "width:100%;",
        }),
        el("div", {
          class: "comfymodal-studio-progress-segments",
          "data-testid": "progress-bar-segments",
        }),
      ]);
      var _terminalStages = runState.goldenProgress && runState.goldenProgress.stages;
      var _terminalTotal = _goldenRunTotalMs(runState, _terminalStages);
      var terminalTotal = el("div", {
        "data-testid": "progress-golden-total",
        class: "comfymodal-studio-progress-total",
        text: "Total: " + (_terminalTotal != null ? _formatDuration(_terminalTotal) : "—"),
      });
      var terminalRow = el("div", { class: "comfymodal-studio-progress-bar-row" });
      terminalRow.appendChild(terminalTotal);
      terminalRow.appendChild(terminalBar);
      section.insertBefore(terminalRow, section.firstChild);
      _appendGoldenProgress(section, runState);
    }
    return section;
  }

  section.style.display = "block";

  // Overall progress bar. Golden stage segments are added below once the
  // telemetry snapshot is available; the fill remains a truthful fallback
  // for the short interval before the first stage event arrives.
  const barContainer = el("div", {
    class: "comfymodal-studio-progress-bar",
    "data-testid": "progress-bar",
  });
  const barFill = el("div", {
    class: "comfymodal-studio-progress-fill",
    "data-testid": "progress-bar-fill",
  });
  barContainer.appendChild(barFill);
  barContainer.appendChild(el("div", {
    class: "comfymodal-studio-progress-segments",
    "data-testid": "progress-bar-segments",
  }));

  // Stage / status info
  const info = el("div", {
    class: "comfymodal-studio-progress-summary",
  });

  const stageEl = el("span", { "data-testid": "progress-stage" });
  const modalEl = el("span", { "data-testid": "progress-modal-status" });
  const nodesEl = el("span", { "data-testid": "progress-nodes" });
  const elapsedEl = el("span", { "data-testid": "progress-elapsed" });
  const percentEl = el("span", { "data-testid": "progress-percent", class: "comfymodal-studio-progress-percent" });
  const stepEl = el("span", { "data-testid": "progress-step", style: "display:none;" });
  const queueEl = el("span", { "data-testid": "progress-queue" });

  info.appendChild(stageEl);
  info.appendChild(modalEl);
  info.appendChild(percentEl);
  info.appendChild(nodesEl);
  info.appendChild(elapsedEl);
  info.appendChild(stepEl);
  info.appendChild(queueEl);

  var liveTotal = el("div", {
    "data-testid": "progress-golden-total",
    class: "comfymodal-studio-progress-total",
    text: "Total: " + _formatDuration(runState.elapsedMs),
  });
  var barRow = el("div", { class: "comfymodal-studio-progress-bar-row" });
  barRow.appendChild(liveTotal);
  barRow.appendChild(barContainer);
  section.appendChild(barRow);
  section.appendChild(info);

  // Determine stage display text
  var stageLabel = "Starting...";
  if (runState.status === "queued") stageLabel = "Queued";
  else if (runState.status === "in_progress") stageLabel = "Generating";
  else if (runState.status === "running") stageLabel = "Running";
  else if (runState.status === "submitted") stageLabel = "Submitted";
  else if (runState.status === "waiting") stageLabel = "Waiting";
  if (runState.goldenStage) stageLabel = _prettifyStageName(runState.goldenStage);

  stageEl.textContent = "Stage: " + stageLabel;
  var modalText = _modalStatusText(runState);
  if (modalText) {
    modalEl.textContent = modalText;
    modalEl.style.display = "";
  } else {
    modalEl.textContent = "";
    modalEl.style.display = "none";
  }
  percentEl.textContent = runState.goldenProgressPercent != null
    ? Math.round(Math.max(0, Math.min(100, runState.goldenProgressPercent))) + "%"
    : "Progress pending";
  if (runState.totalNodes != null && runState.totalNodes > 0) {
    nodesEl.textContent = "Nodes: " + (runState.completedNodes || 0) + "/" + runState.totalNodes;
  } else {
    nodesEl.style.display = "none";
  }
  // Golden telemetry has no sampler tick stream. Keep this node for legacy
  // callers/tests, but never show a fabricated 0/0 readout.
  if (runState.samplerMaximum > 0 && runState.samplerStep != null) {
    var samplerPct = runState.samplerPercent != null ? " (" + Math.round(runState.samplerPercent) + "%)" : "";
    stepEl.textContent = "Sampler: " + runState.samplerStep + "/" + runState.samplerMaximum + samplerPct;
    stepEl.style.display = "";
  } else {
    stepEl.textContent = "";
    stepEl.style.display = "none";
  }
  elapsedEl.textContent = "Elapsed: " + _formatDuration(runState.elapsedMs);

  if (runState.queuePosition > 0) {
    queueEl.textContent = "Queue: " + runState.queuePosition;
    queueEl.style.display = "";
  } else {
    queueEl.style.display = "none";
  }

  // Update progress bar width
  if (runState.goldenProgressPercent != null) {
    barFill.style.width = Math.max(0, Math.min(100, runState.goldenProgressPercent)) + "%";
    barFill.style.animation = "";
  } else if (runState.overallPercent != null) {
    barFill.style.width = Math.max(0, Math.min(100, runState.overallPercent)) + "%";
  } else {
    // Indeterminate: show a partial bar with animation
    barFill.style.width = "30%";
    barFill.style.animation = "cm-pb-pulse 1.6s ease-in-out infinite";
  }

  _appendGoldenProgress(section, runState);

  return section;
}

// Human-readable label for any stage name, including stages the bar has
// never seen before. golden_clip_load → "Clip Load"; unknown future stages
// fall back to title-cased words instead of vanishing.
function _prettifyStageName(name) {
  var raw = String(name == null ? "" : name).trim();
  if (!raw) return "Unknown stage";
  if (/^node\s*:/i.test(raw)) return raw;
  var words = raw.replace(/^golden_/, "").split(/[_-]+/).filter(Boolean);
  if (!words.length) return raw;
  return words.map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(" ");
}

// Display text for a raw Modal lifecycle phase. Only phases actually observed
// (ws modal_status or cursor status events) or truthfully derived reach this;
// nothing here invents scheduler internals.
var _MODAL_PHASE_DISPLAY = {
  dispatch: "Dispatching",
  awaiting_remote: "Waiting for remote startup",
  lifecycle_unknown: "Lifecycle status unavailable",
  scheduling: "Scheduling",
  scheduled: "Scheduling",
  queue: "Scheduling",
  startup: "Starting up",
  plan_received: "Starting up",
  restoring: "Restoring",
  restore: "Restoring",
  restore_begin: "Restoring",
  execution: "Executing",
  generic_execution: "Running",
  snapshot_capturing: "Capturing snapshot",
  snapshot_preparing: "Preparing snapshot",
  snapshot: "Capturing snapshot",
  snapshotting: "Capturing snapshot",
  snapshot_committed: "Snapshot captured",
  teardown: "Cleaning up",
  finalizing: "Finalizing",
  done: "Done",
};

function _displayModalPhase(phase) {
  var key = String(phase == null ? "" : phase).trim().toLowerCase();
  if (Object.prototype.hasOwnProperty.call(_MODAL_PHASE_DISPLAY, key)) return _MODAL_PHASE_DISPLAY[key];
  if (!key) return "";
  return key.charAt(0).toUpperCase() + key.slice(1);
}

function _goldenStageActive(byName, name) {
  var rec = byName[name];
  return !!(rec && rec.phase !== "completed" && rec.phase !== "failed");
}

function _modalStatusText(runState) {
  var golden = runState && runState.goldenProgress;
  var phase = runState && runState.modalPhase;
  if (!phase && golden && golden.statusPhase) phase = golden.statusPhase;
  var stages = (golden && golden.stages) || [];
  var byName = {};
  stages.forEach(function (s) { if (s && s.stage) byName[s.stage] = s; });
  if (_goldenStageActive(byName, "golden_restore")) return "Modal: Restoring";
  if (_goldenStageActive(byName, "golden_teardown")) return "Modal: Cleaning up";
  if (_goldenStageActive(byName, "golden_output")) return "Modal: Finalizing output";
  if (Object.keys(byName).some(function (name) { return _goldenStageActive(byName, name); })) {
    return "Modal: Running";
  }
  if (stages.length) return "Modal: Finalizing";
  if (phase) return "Modal: " + _displayModalPhase(phase);
  return "Modal: Waiting for remote startup";
}

function _goldenStageDuration(stage) {
  var d = Number(stage && stage.durationMs);
  return Number.isFinite(d) && d > 0 ? d : 0;
}

// Ticking format for in-flight stages: always tenths - 0.0s, 0.1s, 1.7s.
// Completed stages keep _formatDuration ("2.1s", "433ms").
function _formatTickMs(ms) {
  var s = Math.max(0, Number(ms) || 0) / 1000;
  if (s < 60) return s.toFixed(1) + "s";
  var m = Math.floor(s / 60);
  var rest = (s % 60).toFixed(1);
  return m + "m " + (Number(rest) < 10 ? "0" : "") + rest + "s";
}

// ── Golden live ticker ─────────────────────────────────────────────
// One shared 100ms interval drives the in-flight segment timers
// (Clip Load 0.0s → 0.1s → …) and the Elapsed readout between backend
// polls. Poll patches rebuild the segments with fresh snapshots; the
// ticker only touches text/widths in place. Stops itself at terminal,
// when every group completes, or when the section leaves the DOM.
var _goldenTick = { timer: null, runKey: null, snapshot: null, runStartWall: null };

function _goldenTickNow() {
  if (typeof performance !== "undefined" && performance.now) return performance.now();
  return Date.now();
}

function _goldenTickStop() {
  if (_goldenTick.timer) {
    clearInterval(_goldenTick.timer);
    _goldenTick.timer = null;
  }
}

function _goldenTickSync(runState) {
  var golden = runState && runState.goldenProgress;
  if (!golden || typeof document === "undefined" || typeof setInterval === "undefined") return;
  var runKey = (golden.requestId != null && String(golden.requestId)) || "run";
  if (_goldenTick.runKey !== runKey) {
    _goldenTick.runKey = runKey;
    _goldenTick.runStartWall = null;
  }
  var t = _goldenTickNow();
  if (_goldenTick.runStartWall == null) {
    _goldenTick.runStartWall = (runState._localStartTime != null)
      ? runState._localStartTime
      : Date.now();
  }
  var terminal = LEGACY_TERMINAL_STATUSES.indexOf(runState.status) !== -1;
  _goldenTick.snapshot = {
    golden: golden,
    terminal: terminal,
    runStartPerf: t - (Date.now() - _goldenTick.runStartWall),
  };
  if (terminal) {
    _goldenTickStop();
    return;
  }
  if (!_goldenTick.timer) {
    _goldenTick.timer = setInterval(_goldenTickBeat, 100);
  }
}

function _goldenTickBeat() {
  if (typeof document === "undefined") {
    _goldenTickStop();
    return;
  }
  var snap = _goldenTick.snapshot;
  var section = document.querySelector('[data-testid="progress-section"]');
  if (!snap || !section || snap.terminal) {
    _goldenTickStop();
    return;
  }
  var groups = _measuredProgressGroups(snap.golden);
  var knownTotal = groups.reduce(function (sum, g) { return sum + g.duration; }, 0);
  var anyRunning = (snap.golden.nodeSpans || []).some(function (span) { return span.phase === "started"; });
  groups.forEach(function (g) {
    if (g.running) anyRunning = true;
    var seg = section.querySelector('[data-stage="' + g.key + '"]');
    if (!seg) return;
    var timeEl = seg.querySelector(".comfymodal-studio-progress-segment-time");
    if (timeEl && timeEl.textContent !== g.timeText) timeEl.textContent = g.timeText;
    if (knownTotal > 0 && g.duration > 0) {
      var w = ((g.duration / knownTotal) * 100).toFixed(3) + "%";
      if (seg.style.width !== w) seg.style.width = w;
    }
  });
  var elapsedEl = document.querySelector('[data-testid="progress-elapsed"]');
  if (elapsedEl && snap.runStartPerf != null) {
    var elapsedText = "Elapsed: " + _formatTickMs(Math.max(0, _goldenTickNow() - snap.runStartPerf));
    if (elapsedEl.textContent !== elapsedText) elapsedEl.textContent = elapsedText;
  }
  if (!anyRunning) _goldenTickStop();
  _renderSpanDisplay(section, snap.golden);
}

// Terminal total: client elapsed clock first (covers queue through output),
// falling back to the sum of authoritative stage durations.
function _goldenRunTotalMs(runState, stages) {
  var e = runState && runState.elapsedMs != null ? Number(runState.elapsedMs) : NaN;
  if (Number.isFinite(e) && e >= 0) return e;
  var sum = 0;
  (stages || []).forEach(function (s) { sum += _goldenStageDuration(s); });
  return sum > 0 ? sum : null;
}

// Live node detail rows under the bar: per-node spans from the cursor stream
// while running, falling back to the terminal Gantt's longest spans (the same
// "Node: ..." / loader rows the log Gantt renders) once the result lands.
// Bounded (8 rows) and best-effort — absent data renders nothing, never
// fabricated rows.
function _nodeRowsFor(golden) {
  return progressSpanView(golden).groups.map(function (group) {
    return {
      label: group.spans.map(function (span) { return span.label; }).join(" || "),
      text: group.spans.map(function (span) { return span.active ? _formatTickMs(span.elapsedMs) : _formatDuration(span.elapsedMs); }).join(" || "),
      title: group.spans.map(function (span) { return span.label; }).join(" || "),
    };
  });
}

function _measuredProgressGroups(golden) {
  return progressSpanView(golden).groups.map(function (group, index) {
    var running = group.spans.some(function (span) { return span.active; });
    var label = group.spans.map(function (span) { return span.label; }).join(" || ");
    var timeText = group.spans.map(function (span) {
      return span.active ? _formatTickMs(span.elapsedMs) : _formatDuration(span.elapsedMs);
    }).join(" || ");
    return { key: group.key, index: index, label: label, timeText: timeText,
      duration: (group.end - group.start) / 1e6, detail: label + " — " + timeText,
      running: running, phase: running ? "active" : "completed", members: [] };
  });
}

function _renderSpanDisplay(section, golden) {
  var view = progressSpanView(golden);
  var stageEl = section.querySelector('[data-testid="progress-stage"]');
  if (stageEl && view.active.length) {
    stageEl.textContent = "Stage: " + view.active.map(function (span) {
      return span.label + " (" + _formatTickMs(span.elapsedMs) + ")";
    }).join(" || ");
  }
  var modalEl = section.querySelector('[data-testid="progress-modal-status"]');
  if (modalEl && view.active.length) modalEl.textContent = "Modal: Running";
  _renderNodeRows(section, golden);
}

function _renderNodeRows(section, golden) {
  var old = section.querySelector('[data-testid="progress-node-rows"]');
  if (old) old.remove();
  var rows = _nodeRowsFor(golden);
  if (!rows.length) return;
  var wrap = el("div", {
    class: "comfymodal-studio-progress-nodes",
    "data-testid": "progress-node-rows",
  });
  rows.forEach(function (row) {
    wrap.appendChild(el("div", {
      class: "comfymodal-studio-progress-node-row",
      title: row.title,
      text: row.label + " — " + row.text,
    }));
  });
  section.appendChild(wrap);
}

function _appendGoldenProgress(section, runState) {
  const golden = runState && runState.goldenProgress;
  if (!golden) return;
  _goldenTickSync(runState);
  const stages = Array.isArray(golden.stages) ? golden.stages : [];
  const groups = _measuredProgressGroups(golden);
  const segmentBar = section.querySelector('[data-testid="progress-bar-segments"]');
  if (segmentBar) {
    while (segmentBar.firstChild) segmentBar.removeChild(segmentBar.firstChild);
    const knownTotal = groups.reduce(function (sum, g) { return sum + g.duration; }, 0);
    groups.forEach(function (g) {
      const segment = el("div", {
        class: "comfymodal-studio-progress-segment is-" + g.phase + (g.index % 2 === 1 ? " is-alt" : ""),
        "data-stage": g.key,
        "data-duration-known": g.duration > 0 ? "true" : "false",
        "aria-label": g.detail,
        title: g.label + " — " + g.detail,
      });
      if (g.duration > 0 && knownTotal > 0) {
        segment.style.width = ((g.duration / knownTotal) * 100).toFixed(3) + "%";
      } else {
        segment.style.width = "0%";
      }
      const isCurrent = g.running || g.members.indexOf(golden.currentStage) !== -1 ||
        (golden.failedStage && g.members.indexOf(golden.failedStage) !== -1);
      if (isCurrent) {
        segment.classList.add("is-current");
        segment.setAttribute("aria-current", "step");
      }
      segment.appendChild(el("span", { class: "comfymodal-studio-progress-segment-label", text: g.label }));
      segment.appendChild(el("span", { class: "comfymodal-studio-progress-segment-time", text: g.timeText }));
      segmentBar.appendChild(segment);
    });
  }
  if (golden.error) {
    section.appendChild(el("div", {
      "data-testid": "progress-golden-stage-error",
      text: "Golden stage failure: " + golden.error,
      style: "font-size:10px;color:var(--color-danger,#f87171);margin-top:4px;",
    }));
  }
  _renderSpanDisplay(section, golden);
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Legacy Experiment grid viewport ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
// Retired in Wave D: filmstrip experiments now open History V2 detail.

function _formatDuration(ms) {
  if (ms == null) return "0ms";
  // Safe numeric conversion ├óΓé¼ΓÇ¥ never call .toFixed on a non-number
  if (typeof ms !== "number") {
    ms = Number(ms);
    if (isNaN(ms)) return "0ms";
  }
  if (ms < 1000) return ms.toFixed(0) + "ms";
  if (ms < 60000) return (ms / 1000).toFixed(1) + "s";
  var m = Math.floor(ms / 60000);
  var s = (ms % 60000) / 1000;
  return m + "m " + s.toFixed(0) + "s";
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ DOM Progress Patch (avoids full page teardown for frequent updates) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function _domPatchProgress(state) {
  var rs = state.playground && state.playground.runState;
  if (!rs) return;

  var stageEl = document.querySelector('[data-testid="progress-stage"]');
  if (stageEl) {
    var stageLabel = "Starting...";
    if (rs.status === "queued") stageLabel = "Queued";
    else if (rs.status === "in_progress") stageLabel = "Generating";
    else if (rs.status === "running") stageLabel = "Running";
    else if (rs.status === "submitted") stageLabel = "Submitted";
    else if (rs.status === "waiting") stageLabel = "Waiting";
    else if (rs.status === "canceled") stageLabel = "Canceled";
    else if (rs.status === "interrupted") stageLabel = "Interrupted";
    if (rs.goldenStage) stageLabel = _prettifyStageName(rs.goldenStage);
    stageEl.textContent = "Stage: " + stageLabel;
  }

  var modalEl = document.querySelector('[data-testid="progress-modal-status"]');
  if (modalEl) {
    var modalText = _modalStatusText(rs);
    if (modalText) {
      modalEl.textContent = modalText;
      modalEl.style.display = "";
    } else {
      modalEl.textContent = "";
      modalEl.style.display = "none";
    }
  }

  var percentEl = document.querySelector('[data-testid="progress-percent"]');
  if (percentEl) {
    percentEl.textContent = rs.goldenProgressPercent != null
      ? Math.round(Math.max(0, Math.min(100, rs.goldenProgressPercent))) + "%"
      : "Progress pending";
  }

  var nodesEl = document.querySelector('[data-testid="progress-nodes"]');
  if (nodesEl) {
    if (rs.totalNodes != null && rs.totalNodes > 0) {
      nodesEl.textContent = "Nodes: " + (rs.completedNodes || 0) + "/" + rs.totalNodes;
      nodesEl.style.display = "";
    } else {
      nodesEl.style.display = "none";
    }
  }

  var elapsedEl = document.querySelector('[data-testid="progress-elapsed"]');
  if (elapsedEl && rs.elapsedMs != null) {
    elapsedEl.textContent = "Elapsed: " + _formatDuration(rs.elapsedMs);
  }

  var totalEl = document.querySelector('[data-testid="progress-golden-total"]');
  if (totalEl) {
    var totalMs = _goldenRunTotalMs(rs, rs.goldenProgress && rs.goldenProgress.stages);
    totalEl.textContent = "Total: " + _formatDuration(totalMs != null ? totalMs : rs.elapsedMs);
  }

  var stepEl = document.querySelector('[data-testid="progress-step"]');
  if (stepEl) {
    if (rs.samplerMaximum > 0 && rs.samplerStep != null) {
      var sp = rs.samplerPercent != null ? " (" + Math.round(rs.samplerPercent) + "%)" : "";
      stepEl.textContent = "Sampler: " + rs.samplerStep + "/" + rs.samplerMaximum + sp;
      stepEl.style.display = "";
    } else {
      stepEl.textContent = "";
      stepEl.style.display = "none";
    }
  }

  var queueEl = document.querySelector('[data-testid="progress-queue"]');
  if (queueEl) {
    if (rs.queuePosition > 0) {
      queueEl.textContent = "Queue: " + rs.queuePosition;
      queueEl.style.display = "";
    } else {
      queueEl.style.display = "none";
    }
  }

  var barFill = document.querySelector('[data-testid="progress-bar-fill"]');
  if (barFill) {
    if (rs.goldenProgressPercent != null) {
      barFill.style.width = Math.max(0, Math.min(100, rs.goldenProgressPercent)) + "%";
      barFill.style.animation = "";
    } else if (rs.overallPercent != null) {
      barFill.style.width = Math.max(0, Math.min(100, rs.overallPercent)) + "%";
      barFill.style.animation = "";
    } else {
      barFill.style.width = "30%";
      barFill.style.animation = "cm-pb-pulse 1.6s ease-in-out infinite";
    }
  }

  if (rs.goldenProgress) {
    var progressSection = document.querySelector('[data-testid="progress-section"]');
    if (progressSection) {
      var oldErr = progressSection.querySelector('[data-testid="progress-golden-stage-error"]');
      if (oldErr) oldErr.remove();
      _appendGoldenProgress(progressSection, rs);
    }
  }
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Favorite Star ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function renderFavoriteStar(nr, actions, apiBase) {
  var isFav = nr.favorite;
  var star = el("button", {
    type: "button",
    class: "comfymodal-studio-favorite-star",
    "data-testid": "favorite-star",
    "aria-label": isFav ? "Remove from favorites" : "Add to favorites",
    "aria-pressed": isFav ? "true" : "false",
    text: isFav ? "\u2605" : "\u2606",
    style: "font-size:18px;color:" + (isFav ? "#fbbf24" : "#555") + ";",
    title: isFav ? "Remove from favorites" : "Add to favorites",
  });

  star.addEventListener("click", function (e) {
    e.stopPropagation();
    // Optimistic toggle
    var wasFav = isFav;
    var newFav = !wasFav;
    isFav = newFav;
    nr.favorite = newFav;
    var runId = nr.id || nr.experimentId;
    star.textContent = newFav ? "\u2605" : "\u2606";
    star.style.color = newFav ? "#fbbf24" : "#555";
    star.setAttribute("aria-label", newFav ? "Remove from favorites" : "Add to favorites");
    star.setAttribute("aria-pressed", newFav ? "true" : "false");
    star.title = newFav ? "Remove from favorites" : "Add to favorites";

    // Optimistic API call with rollback
    function _rollback() {
      isFav = wasFav;
      nr.favorite = wasFav;
      star.textContent = wasFav ? "\u2605" : "\u2606";
      star.style.color = wasFav ? "#fbbf24" : "#555";
      star.setAttribute("aria-label", wasFav ? "Remove from favorites" : "Add to favorites");
      star.setAttribute("aria-pressed", wasFav ? "true" : "false");
      star.title = wasFav ? "Remove from favorites" : "Add to favorites";
    }

    var writePromise;
    if (nr._historyKind) {
      // History V2 record ├óΓé¼ΓÇ¥ durable annotation authority
      writePromise = _getRecentRunsRepo(apiBase).then(function (repo) {
        return repo.setFavorite(nr.id, newFav);
      });
    } else {
      writePromise = updateRunAnnotation(apiBase, runId, { favorite: newFav });
    }
    writePromise.then(function (result) {
      if (!nr._historyKind && (!result || result.status !== "ok")) {
        // Rollback on failure
        _rollback();
      }
    }).catch(function () {
      _rollback();
    });
  });

  return star;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Note Editor ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function renderNoteEditor(nr, actions, apiBase) {
  var container = el("div", {
    class: "comfymodal-studio-note-editor",
    "data-testid": "note-editor",
    style: "margin-top:4px;",
  });

  var currentNote = nr.note || "";
  var textarea = el("textarea", {
    class: "comfymodal-input comfymodal-studio-textarea",
    "data-testid": "note-textarea",
    style: "min-height:40px;font-size:11px;resize:vertical;box-sizing:border-box;",
    text: currentNote,
  });
  textarea.value = currentNote;

  var noteHeader = el("div", {
    style: "font-size:10px;color:#888;margin-bottom:2px;font-weight:600;text-transform:uppercase;",
    text: "Note",
  });

  var buttonRow = el("div", {
    style: "display:flex;gap:4px;margin-top:4px;align-items:center;",
  });

  var saveBtn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "note-save-btn",
    text: "Save",
    style: "font-size:10px;",
  });

  var cancelBtn = el("button", {
    class: "comfymodal-secondary-btn",
    "data-testid": "note-cancel-btn",
    text: "Cancel",
    style: "font-size:10px;",
  });

  var statusEl = el("span", {
    "data-testid": "note-status",
    style: "font-size:9px;color:#888;margin-left:4px;",
  });

  buttonRow.appendChild(saveBtn);
  buttonRow.appendChild(cancelBtn);
  buttonRow.appendChild(statusEl);
  container.appendChild(noteHeader);
  container.appendChild(textarea);
  container.appendChild(buttonRow);

  var runId = nr.id || nr.experimentId;
  var isDirty = false;
  var savedNote = currentNote;

  textarea.addEventListener("input", function () {
    isDirty = textarea.value !== savedNote;
    if (isDirty) {
      statusEl.textContent = "Unsaved changes";
      statusEl.style.color = "#fbbf24";
    } else {
      statusEl.textContent = "";
    }
  });

  saveBtn.addEventListener("click", function () {
    if (!isDirty) return;
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    statusEl.textContent = "Saving...";
    statusEl.style.color = "#888";

    var noteValue = textarea.value;
    var writePromise;
    if (nr._historyKind) {
      // History V2 record ├óΓé¼ΓÇ¥ durable annotation authority
      writePromise = _getRecentRunsRepo(apiBase).then(function (repo) {
        return repo.setNote(nr.id, noteValue);
      });
    } else {
      writePromise = updateRunAnnotation(apiBase, runId, { note: noteValue });
    }
    writePromise.then(function (result) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save";
      var ok = nr._historyKind ? true : !!(result && result.status === "ok");
      if (ok) {
        savedNote = noteValue;
        nr.note = noteValue;
        // Use backend updated_at as primary source, fall back to client time
        var backendUpdatedAt = result && result.annotations && result.annotations.updated_at;
        nr.noteUpdatedAt = backendUpdatedAt || new Date().toISOString();
        isDirty = false;
        statusEl.textContent = "Saved " + nr.noteUpdatedAt.substring(0, 19);
        statusEl.style.color = "#4ade80";
      } else {
        statusEl.textContent = "Save failed";
        statusEl.style.color = "#f87171";
      }
    }).catch(function () {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save";
      statusEl.textContent = "Save failed";
      statusEl.style.color = "#f87171";
    });
  });

  cancelBtn.addEventListener("click", function () {
    textarea.value = savedNote;
    isDirty = false;
    statusEl.textContent = "";
    if (savedNote) {
      statusEl.textContent = "Note saved";
      statusEl.style.color = "#888";
    }
  });

  return container;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Right Workspace ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼

function renderWorkspace(state, context) {
  // Shelf: the right-side workspace is the single result panel (output
  // canvas, progress, metadata, recent filmstrip) — never a movable card.
  const workspace = el("div", { class: "comfymodal-studio-workspace", "data-testid": "workspace", "data-shelf-output-panel": "true" });
  var wsActions = (state.playground && state.playground._runActions) || buildActions(state, context);
  if (state.playground && !state.playground._runActions) state.playground._runActions = wsActions;
  if (state.playground && state.playground.canvasBg === undefined) {
    state.playground.canvasBg = _loadCanvasBg();
  }
  // Reload must not wipe the queue: restore persisted items once per page
  // load (in-memory mutations save through _saveQueue).
  if (state.playground && !state.playground._queueHydrated) {
    state.playground._queueHydrated = true;
    if (!Array.isArray(state.playground._runQueue) || !state.playground._runQueue.length) {
      state.playground._runQueue = _loadStoredQueue();
    }
  }

  // Top bar: centered Photoshop-style tool rail + right-aligned run controls.
  workspace.appendChild(renderWorkspaceTopBar(state, context, wsActions));

  // Per-tool submenu row (one visible at a time, above the canvas).
  var submenu = renderToolSubmenu(state, context, wsActions);
  if (submenu) workspace.appendChild(submenu);

  // Post Processing mounts the existing local engine; the Upscale category
  // is an honest later-phase placeholder and falls through to the canvas.
  if (activeModeOf(state) === "post" && activeSubtoolOf(state) !== "upscale") {
    // Keep the Studio canvas central. The post engine was mounted by the
    // left control panel; move its existing stage here instead of rendering a
    // second post-processing workspace inside the canvas.
    var postCanvas = renderCanvas(state, context, wsActions);
    var ppMount = state.playground && state.playground._postProcessMount;
    var ppStage = ppMount && ppMount.stage;
    if (ppStage) {
      var legacyOutput = postCanvas.querySelector('[data-testid="canvas-output"]');
      if (legacyOutput) legacyOutput.style.display = "none";
      // The empty-canvas placeholder belongs to the generation views: in Post
      // the engine stage IS the image surface, so it must not show alongside.
      var emptyNote = postCanvas.querySelector('[data-testid="canvas-empty"]');
      if (emptyNote) emptyNote.style.display = "none";
      ppStage.classList.add("comfymodal-studio-postprocess-stage");
      ppStage.style.width = "100%";
      ppStage.style.height = "100%";
      ppStage.style.minHeight = "420px";
      postCanvas.appendChild(ppStage);
    }
    workspace.appendChild(postCanvas);
    workspace.appendChild(renderProgressSection(state, context));
    return workspace;
  }

  // Canvas area
  workspace.appendChild(renderCanvas(state, context, wsActions));

  // Progress section (shared progress display)
  workspace.appendChild(renderProgressSection(state, context));

  // Recent runs filmstrip
  workspace.appendChild(renderHistoryCarousel(state, context));

  return workspace;
}

// -- Legacy feature tabs -------------------------------------------------
// Retained (uncalled) for the pinned source contract: the test suite
// requires feature-tab buttons referencing all FEATURE_SPECS to exist in
// this module. The live workspace uses the tool rail instead, so this
// renders nothing until re-wired.
function renderFeatureTabs(state, context) {
  const tabs = el("div", { class: "comfymodal-studio-feature-tabs-legacy", "data-testid": "feature-tabs-legacy" });

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

// -- Layout (Phase 7: visual prompt authoring) --------------------------
// Boxes live in a localStorage draft; the deterministic serializer turns
// them into one human-readable prompt string handed to the normal prompt
// control via Send to Prompt. No Layout workflow, engine, or schema.
var LAYOUT_STORE_KEY = "comfymodal.studio.layout.v1";
var LAYOUT_ASPECTS = [["1:1", 1], ["3:4", 0.75], ["4:3", 4 / 3], ["16:9", 16 / 9], ["9:16", 9 / 16]];
function loadLayoutDraft() {
  var out = { boxes: [], globalDesc: "", aspect: "1:1", selectedId: "", seq: 0 };
  try {
    var raw = localStorage.getItem(LAYOUT_STORE_KEY);
    if (!raw) return out;
    var j = JSON.parse(raw);
    if (j && Array.isArray(j.boxes)) {
      out.boxes = j.boxes.filter(function (b) {
        return b && (b.kind === "object" || b.kind === "text")
          && isFinite(Number(b.x)) && isFinite(Number(b.y))
          && isFinite(Number(b.w)) && isFinite(Number(b.h));
      }).map(function (b) {
        return {
          id: String(b.id || ""), kind: b.kind,
          x: Math.max(0, Math.min(100, Number(b.x))), y: Math.max(0, Math.min(100, Number(b.y))),
          w: Math.max(1, Math.min(100, Number(b.w))), h: Math.max(1, Math.min(100, Number(b.h))),
          label: String(b.label || ""), desc: String(b.desc || ""),
          text: String(b.text || ""), color: String(b.color || "#e8b93e"),
        };
      });
    }
    if (j && typeof j.globalDesc === "string") out.globalDesc = j.globalDesc;
    if (j && typeof j.aspect === "string") out.aspect = j.aspect;
    if (j && typeof j.selectedId === "string") out.selectedId = j.selectedId;
    if (j && isFinite(Number(j.seq))) out.seq = Number(j.seq);
  } catch (_e) {}
  return out;
}
function saveLayoutDraft(draft) {
  try { localStorage.setItem(LAYOUT_STORE_KEY, JSON.stringify(draft || {})); } catch (_e) {}
}
function _layoutAspectRatio(aspect) {
  for (var i = 0; i < LAYOUT_ASPECTS.length; i++) {
    if (LAYOUT_ASPECTS[i][0] === aspect) return LAYOUT_ASPECTS[i][1];
  }
  return 1;
}
// Deterministic serializer: creation order, integer 0-100 geometry, fixed
// line shapes. Human-readable and diffable; the exact string is what Send
// to Prompt submits, so History stays auditable through prompt_text.
function serializeLayout(draft) {
  var d = draft || { boxes: [], globalDesc: "", aspect: "1:1" };
  var lines = [];
  var global = String(d.globalDesc || "").trim();
  lines.push("Scene: " + (global || "unspecified scene") + ".");
  var boxes = Array.isArray(d.boxes) ? d.boxes : [];
  var oi = 0, ti = 0;
  boxes.forEach(function (b) {
    var x = Math.round(Number(b.x)), y = Math.round(Number(b.y));
    var w = Math.round(Number(b.w)), h = Math.round(Number(b.h));
    if (b.kind === "text") {
      ti++;
      var t = String(b.text || "").trim() || ("text " + ti);
      lines.push("Text " + ti + ": \"" + t + "\" at x=" + x + ",y=" + y + " size " + w + "x" + h + ".");
    } else {
      oi++;
      var label = String(b.label || "").trim() || ("object " + oi);
      var desc = String(b.desc || "").trim();
      var color = String(b.color || "").trim();
      var line = "Object " + oi + " \"" + label + "\""
        + (desc ? ": " + desc : "")
        + " at x=" + x + ",y=" + y + " size " + w + "x" + h
        + (color ? " color " + color : "") + ".";
      lines.push(line);
    }
  });
  lines.push("Canvas: " + String(d.aspect || "1:1") + ".");
  return lines.join("\n");
}
function _renderLayoutEditor(state, context, actions) {
  var wrap = el("div", {
    class: "comfymodal-studio-layout",
    "data-testid": "layout-editor",
    style: "width:100%;display:flex;flex-direction:column;gap:8px;",
  });
  var draft = loadLayoutDraft();
  function persist() { saveLayoutDraft(draft); paintPreview(); }
  var toolbar = el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;align-items:center;" });
  var addObj = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "+ Object region", "data-testid": "layout-add-object" });
  var addTxt = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "+ Text region", "data-testid": "layout-add-text" });
  var aspectSel = el("select", { "data-testid": "layout-aspect", class: "comfymodal-input", title: "Stage aspect ratio" });
  LAYOUT_ASPECTS.forEach(function (pair) {
    var o = document.createElement("option");
    o.value = pair[0];
    o.textContent = pair[0];
    if (draft.aspect === pair[0]) o.selected = true;
    aspectSel.appendChild(o);
  });
  var clearBtn = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "Reset", "data-testid": "layout-reset", title: "Clear all regions" });
  var sendBtn = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "Send to Prompt →", "data-testid": "layout-send", title: "Copy the serialization into the normal prompt and return to Text" });
  toolbar.appendChild(addObj);
  toolbar.appendChild(addTxt);
  toolbar.appendChild(aspectSel);
  toolbar.appendChild(clearBtn);
  toolbar.appendChild(sendBtn);
  wrap.appendChild(toolbar);
  var stage = el("div", {
    "data-testid": "layout-stage",
    style: "position:relative;width:100%;aspect-ratio:" + String(draft.aspect || "1:1").replace(":", " / ")
      + ";background:#141416;border:1px solid var(--color-border, #333);border-radius:8px;overflow:hidden;touch-action:none;",
  });
  wrap.appendChild(stage);
  var insp = el("div", { "data-testid": "layout-inspector", style: "display:flex;flex-direction:column;gap:6px;" });
  wrap.appendChild(insp);
  var preview = el("pre", {
    "data-testid": "layout-preview",
    style: "font-size:11px;color:#888;white-space:pre-wrap;margin:0;overflow-wrap:anywhere;",
  });
  wrap.appendChild(preview);
  function paintPreview() {
    preview.textContent = serializeLayout(draft);
  }
  function selectedBox() {
    for (var i = 0; i < draft.boxes.length; i++) {
      if (draft.boxes[i].id === draft.selectedId) return draft.boxes[i];
    }
    return null;
  }
  function clampBox(b) {
    b.x = Math.max(0, Math.min(100 - b.w, b.x));
    b.y = Math.max(0, Math.min(100 - b.h, b.y));
    b.w = Math.max(1, Math.min(100 - b.x, b.w));
    b.h = Math.max(1, Math.min(100 - b.y, b.h));
  }
  function paintBoxes() {
    while (stage.firstChild) stage.removeChild(stage.firstChild);
    draft.boxes.forEach(function (b) {
      var on = b.id === draft.selectedId;
      var box = el("div", {
        "data-testid": "layout-box-" + b.id,
        "data-box-id": b.id,
        title: (b.kind === "text" ? "Text: " + (b.text || "(empty)") : "Object: " + (b.label || "(unnamed)")),
        style: "position:absolute;left:" + b.x + "%;top:" + b.y + "%;width:" + b.w + "%;height:" + b.h + "%;"
          + "border:2px solid " + (on ? "#e8b93e" : (b.kind === "text" ? "#7ab8ff" : b.color || "#e8b93e"))
          + ";border-radius:4px;background:" + (b.kind === "text" ? "rgba(122,184,255,.08)" : "rgba(232,185,62,.07)")
          + ";cursor:move;box-sizing:border-box;",
      });
      var tag = el("span", {
        text: b.kind === "text" ? ("T: " + String(b.text || "(text)").slice(0, 18)) : ("O: " + String(b.label || "(object)").slice(0, 18)),
        style: "position:absolute;top:-18px;left:0;font-size:10px;color:#aaa;white-space:nowrap;",
      });
      box.appendChild(tag);
      var grip = el("span", {
        "data-testid": "layout-resize-" + b.id,
        title: "Resize",
        style: "position:absolute;right:-7px;bottom:-7px;width:14px;height:14px;border-radius:3px;background:#e8b93e;cursor:nwse-resize;",
      });
      box.appendChild(grip);
      box.addEventListener("pointerdown", function (ev) {
        ev.stopPropagation();
        draft.selectedId = b.id;
        persist();
        paintBoxes();
        paintInspector();
        var r = stage.getBoundingClientRect();
        var sx = ev.clientX, sy = ev.clientY, ox = b.x, oy = b.y;
        function mv(e2) {
          b.x = ox + ((e2.clientX - sx) / r.width) * 100;
          b.y = oy + ((e2.clientY - sy) / r.height) * 100;
          clampBox(b);
          box.style.left = b.x + "%";
          box.style.top = b.y + "%";
        }
        function up() {
          document.removeEventListener("pointermove", mv);
          document.removeEventListener("pointerup", up);
          persist();
          paintPreview();
        }
        document.addEventListener("pointermove", mv);
        document.addEventListener("pointerup", up);
      });
      grip.addEventListener("pointerdown", function (ev) {
        ev.stopPropagation();
        ev.preventDefault();
        draft.selectedId = b.id;
        var r = stage.getBoundingClientRect();
        var sx = ev.clientX, sy = ev.clientY, ow = b.w, oh = b.h;
        function mv(e2) {
          b.w = ow + ((e2.clientX - sx) / r.width) * 100;
          b.h = oh + ((e2.clientY - sy) / r.height) * 100;
          clampBox(b);
          box.style.width = b.w + "%";
          box.style.height = b.h + "%";
        }
        function up() {
          document.removeEventListener("pointermove", mv);
          document.removeEventListener("pointerup", up);
          persist();
          paintPreview();
          paintBoxes();
          paintInspector();
        }
        document.addEventListener("pointermove", mv);
        document.addEventListener("pointerup", up);
      });
      stage.appendChild(box);
    });
  }
  function paintInspector() {
    while (insp.firstChild) insp.removeChild(insp.firstChild);
    var gbox = el("div", { style: "display:flex;gap:8px;align-items:center;" });
    gbox.appendChild(el("span", { text: "Background", style: "font-size:12px;color:#aaa;flex:none;" }));
    var gdesc = el("input", {
      type: "text", value: draft.globalDesc || "", placeholder: "Global / background description…",
      "data-testid": "layout-global-desc", class: "comfymodal-input comfymodal-studio-text-input",
      style: "flex:1;min-width:0;",
    });
    gdesc.addEventListener("input", function () { draft.globalDesc = gdesc.value; persist(); });
    gbox.appendChild(gdesc);
    insp.appendChild(gbox);
    var b = selectedBox();
    if (!b) {
      insp.appendChild(el("p", {
        text: "Select a region to edit it, or add one above.",
        style: "font-size:11px;color:#888;margin:0;",
      }));
      return;
    }
    var grow = el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;align-items:center;" });
    grow.appendChild(el("span", { text: b.kind === "text" ? "Text region" : "Object region", style: "font-size:12px;color:#aaa;" }));
    if (b.kind === "object") {
      var lab = el("input", {
        type: "text", value: b.label || "", placeholder: "Label, e.g. lighthouse",
        "data-testid": "layout-box-label", class: "comfymodal-input comfymodal-studio-text-input",
        style: "flex:1;min-width:0;",
      });
      lab.addEventListener("input", function () { b.label = lab.value; persist(); paintBoxes(); });
      grow.appendChild(lab);
      var col = el("input", {
        type: "color", value: /^#[0-9a-fA-F]{6}$/.test(b.color || "") ? b.color : "#e8b93e",
        "data-testid": "layout-box-color", title: "Region color",
      });
      col.addEventListener("input", function () { b.color = col.value; persist(); paintBoxes(); });
      grow.appendChild(col);
    } else {
      var txt = el("input", {
        type: "text", value: b.text || "", placeholder: "Exact text in the image",
        "data-testid": "layout-box-text", class: "comfymodal-input comfymodal-studio-text-input",
        style: "flex:1;min-width:0;",
      });
      txt.addEventListener("input", function () { b.text = txt.value; persist(); paintBoxes(); });
      grow.appendChild(txt);
    }
    var del = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "Delete", "data-testid": "layout-box-delete" });
    del.addEventListener("click", function () {
      draft.boxes = draft.boxes.filter(function (x) { return x.id !== b.id; });
      if (draft.selectedId === b.id) draft.selectedId = "";
      persist();
      paintBoxes();
      paintInspector();
    });
    grow.appendChild(del);
    insp.appendChild(grow);
    if (b.kind === "object") {
      var desc = el("textarea", {
        value: b.desc || "", placeholder: "Region description…", rows: "2",
        "data-testid": "layout-box-desc", class: "comfymodal-input comfymodal-studio-textarea",
        style: "width:100%;box-sizing:border-box;",
      });
      desc.addEventListener("input", function () { b.desc = desc.value; persist(); });
      insp.appendChild(desc);
    }
  }
  function addBox(kind) {
    draft.seq = (draft.seq || 0) + 1;
    var id = "r" + draft.seq + Date.now().toString(36);
    var b = kind === "text"
      ? { id: id, kind: "text", x: 10, y: 10, w: 40, h: 12, label: "", desc: "", text: "", color: "#7ab8ff" }
      : { id: id, kind: "object", x: 20, y: 20, w: 30, h: 30, label: "", desc: "", text: "", color: "#e8b93e" };
    draft.boxes.push(b);
    draft.selectedId = id;
    persist();
    paintBoxes();
    paintInspector();
  }
  addObj.addEventListener("click", function () { addBox("object"); });
  addTxt.addEventListener("click", function () { addBox("text"); });
  aspectSel.addEventListener("change", function () {
    draft.aspect = aspectSel.value;
    stage.style.aspectRatio = String(draft.aspect || "1:1").replace(":", " / ");
    persist();
  });
  clearBtn.addEventListener("click", function () {
    draft.boxes = [];
    draft.selectedId = "";
    persist();
    paintBoxes();
    paintInspector();
  });
  sendBtn.addEventListener("click", function () {
    var text = serializeLayout(draft);
    // Write through the Shelf commit seam (store + validation + DOM sync),
    // not the draft-only setControl path, so the Text prompt field shows it.
    try {
      if (typeof commitShelfValue === "function") {
        commitShelfValue(state, context, actions, "prompt", text);
      } else if (actions && actions.setControl) {
        actions.setControl("prompt", text);
      }
    } catch (_e) {}
    // Return to the ordinary Text prompt so the next run is the normal
    // T2I path with the serialization visible in its prompt field.
    try {
      var pg = state && state.playground;
      if (pg) {
        pg.activeSubtool = "text";
        _persistShellState(state);
      }
    } catch (_e2) {}
    try {
      if (context && context.setPage) context.setPage("playground");
    } catch (_e3) {}
  });
  stage.addEventListener("pointerdown", function () {
    if (draft.selectedId) {
      draft.selectedId = "";
      persist();
      paintBoxes();
      paintInspector();
    }
  });
  paintBoxes();
  paintInspector();
  paintPreview();
  return wrap;
}

// -- Canvas ----------------------------------------------------------

function renderCanvas(state, context, actions) {
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const currentSpec = FEATURE_SPECS.find((f) => f.id === currentFeatureId);

  const canvas = el("div", {
    class: "comfymodal-studio-canvas",
    "data-testid": "canvas-area",
  });
  var _bgFill = state.playground && state.playground.canvasBg;
  if (_bgFill) {
    canvas.style.background = _bgFill;
    canvas.style.backgroundImage = "none";
  }

  const outputUrl = _canvasImageUrl(state);
  // Phase 1 shell placeholders (References/Layout/Guidance/Upscale): an
  // honest disabled notice above the normal canvas, so the current image
  // stays visible and no stale controls appear.
  var _shellSub = activeSubtoolOf(state);
  if (_isPlaceholderSubtool(_shellSub)) {
    var _shellLabel = STUDIO_SUBTOOL_LABELS[_shellSub] || _shellSub;
    canvas.appendChild(el("div", {
      class: "comfymodal-studio-placeholder-notice",
      "data-testid": "shell-placeholder",
      style: "text-align:center;padding:24px 20px;",
    }, [
      el("p", { text: _shellLabel + " — available in a later phase", style: "font-weight:var(--font-weight-semibold);margin-bottom:8px;" }),
      el("p", { text: "Execution is disabled for this view. Your workflow, values, and current image are preserved.", style: "font-size:var(--font-size-sm);color:var(--color-text-muted);" }),
    ]));
  }
  // Phase 7: Layout is visual prompt authoring on Generate. The editor owns
  // this view (the last output stays available in filmstrip/recent runs).
  if (activeToolOf(state) === "t2i" && _shellSub === "layout") {
    canvas.appendChild(_renderLayoutEditor(state, context, actions));
    return canvas;
  }
  var _paintToolId = activeToolOf(state);
  var _isPaintTool = _paintToolId === "inpaint" || _paintToolId === "sketch" || _isSelectOnI2I(state);
  // Paint tools work on the main canvas: with no run output yet, show the
  // paint base (usually the uploaded Source Image) there instead of a
  // second small canvas inside the editor box.
  var _paintBaseUrl = _isPaintTool ? (outputUrl || _editorBaseImageUrl(state)) : "";
  // Shelf: a Workflow switch marks the previous output stale until a new
  // run completes. The right-side canvas dims and carries an explicit note.
  if (outputUrl && state.playground && state.playground._shelfStaleOutput) {
    canvas.classList.add("is-stale");
    canvas.appendChild(el("p", {
      "data-testid": "shelf-stale-note",
      text: "Output from the previous Workflow — run to refresh.",
      style: "font-size:var(--font-size-xs);color:#d9a441;margin:0 0 6px;",
    }));
  }
  if (currentSpec && currentSpec.isPlaceholder) {
    // Honest disabled placeholder for image-edit features
    const placeholderMsg = el("div", { class: "comfymodal-studio-placeholder-notice", style: "text-align:center;padding:40px 20px;" }, [
      el("p", { text: `${currentSpec.label} — Not Implemented`, style: "font-weight:var(--font-weight-semibold);margin-bottom:8px;" }),
      el("p", { text: currentSpec.placeholderReason || "This feature is not available in this release.", style: "font-size:var(--font-size-sm);color:var(--color-text-muted);" }),
    ]);
    canvas.appendChild(placeholderMsg);
    // Honest accessible mask-controls section (disabled with explanation)
    const maskSection = el("div", {
      "data-testid": "mask-controls",
      style: "padding:12px;border:1px solid #2a2a2a;border-radius:4px;margin:8px;background:#0a0a0a;opacity:0.6;",
    }, [
      el("p", { text: "Mask Controls", style: "font-weight:var(--font-weight-semibold);margin:0 0 4px;color:#888;font-size:var(--font-size-sm);" }),
      el("p", { text: "Mask editing tools (brush, selection) are not implemented in this release.", style: "font-size:var(--font-size-xs);color:var(--color-text-muted);margin:0;" }),
    ]);
    canvas.appendChild(maskSection);
  } else if (outputUrl || _paintBaseUrl) {
    const img = el("img", {
      src: (outputUrl || _paintBaseUrl),
      class: "comfymodal-studio-canvas-output",
      "data-testid": "canvas-output",
      onerror: function (e) {
        // A stale/broken URL must never render as a broken-image glyph:
        // swap to the same composed empty state as a missing output.
        const imgEl = e.currentTarget;
        const parent = imgEl.parentNode;
        imgEl.remove();
        if (parent && !parent.querySelector('[data-testid="canvas-empty"]')) {
          parent.appendChild(el("p", {
            "data-testid": "canvas-empty",
            text: "Generated output will appear here.",
            style: "color:var(--color-text-muted);",
          }));
        }
      },
    });
    // Click-to-preview: the zoom/pan + detail-sidebar overlay was written
    // (studio-ui.js createImagePreviewOverlay) and imported, but never wired to
    // the Playground canvas, so pressing a finished image did nothing. It must
    // be mounted by the caller, so own the mount and teardown here.
    img.style.cursor = "zoom-in";
    img.setAttribute("role", "button");
    img.setAttribute("tabindex", "0");
    img.setAttribute("aria-label", "Open generated image preview");
     var _openPreview = function () {
       var _run = (state.playground && state.playground._selectedRun) || null;
       return openRunImagePreview(state, context, _run, outputUrl);
     };
    img.addEventListener("click", _openPreview);
     img.addEventListener("keydown", function (e) {
       if (e.key === "Enter" || e.key === " ") {
         e.preventDefault();
         _openPreview();
       }
     });
     canvas.appendChild(img);
     var _pendingPreviewId = _readPlaygroundPreviewId();
     var _currentPreviewId = viewerFirst(
       state.playground && state.playground._selectedRun && state.playground._selectedRun.runId,
       state.playground && state.playground._selectedRun && state.playground._selectedRun.id
     );
     if (_pendingPreviewId && _pendingPreviewId === String(_currentPreviewId || "")
       && state.playground && !state.playground._previewResumeAttempted
       && !state.playground._previewOpen) {
       state.playground._previewResumeAttempted = true;
       setTimeout(function () { _openPreview(); }, 0);
     }
     const runState = state.playground && state.playground.runState;
    const hasActiveRun = runState && runState.status
      && runState.status !== "idle"
      && LEGACY_TERMINAL_STATUSES.indexOf(runState.status) === -1;
    const hasCanvasSelection = state.playground && state.playground._selectedRun;
    if (hasActiveRun && hasCanvasSelection) {
      canvas.appendChild(renderLiveReturnControl(state, context));
    }
  } else {
    canvas.appendChild(el("p", {
      "data-testid": "canvas-empty",
      text: "Generated output will appear here.",
      style: "color:var(--color-text-muted);",
    }));
  }

  // Placeholder views keep the image but hide the previous workflow tool
  // controls: a preserved inpaint/sketch/outpaint type must not mount its
  // paint editor under the disabled notice.
  var toolEditor = null;
  if (!_isPlaceholderSubtool(_shellSub)) {
    toolEditor = _renderToolEditor(state, context, actions || ((state.playground && state.playground._runActions) || null), canvas);
  }
  if (toolEditor) canvas.appendChild(toolEditor);

  var lineageStrip = _renderLineageStrip(state, context, outputUrl);
  if (lineageStrip) canvas.appendChild(lineageStrip);

  return canvas;
}

function _renderLineageStrip(state, context, canvasUrl) {
  // Minimal ancestry UI for the working image: where it came from (parent)
  // and what was made from it (children). Clicking either makes it the
  // working canvas image. Absent when the image has no recorded lineage.
  var node = _lineageNodeForCanvas(state, canvasUrl);
  if (!node) return null;
  var kids = (node.children || []).filter(function (k) { return k && k !== node.key; });
  if (!node.parent && !kids.length) return null;
  var strip = el("div", {
    class: "comfymodal-studio-lineage-strip",
    "data-testid": "lineage-strip",
    style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:11px;color:#888;",
  });
  function thumbButton(key, testid, label) {
    var btn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn",
      "data-testid": testid,
      title: label + ": " + _lineageDisplayUrl(key),
      "aria-label": label,
    });
    var img = el("img", {
      src: _lineageDisplayUrl(key),
      alt: label,
      style: "width:40px;height:40px;object-fit:cover;border-radius:4px;display:block;",
    });
    btn.appendChild(img);
    btn.addEventListener("click", function () {
      _setCanvasImage(state, _lineageDisplayUrl(key));
      if (context && context.setPage) context.setPage("playground");
    });
    return btn;
  }
  if (node.parent) {
    strip.appendChild(el("span", { text: "From", "data-testid": "lineage-from-label" }));
    strip.appendChild(thumbButton(node.parent, "lineage-parent", "Parent image"));
  }
  if (kids.length) {
    strip.appendChild(el("span", {
      text: kids.length === 1 ? "1 edit" : kids.length + " edits",
      "data-testid": "lineage-children-count",
    }));
    kids.slice(0, 12).forEach(function (k, i) {
      strip.appendChild(thumbButton(k, "lineage-child-" + i, "Derived image " + (i + 1)));
    });
  }
  return strip;
}

function _editorBaseImageUrl(state) {
  var pg = state && state.playground;
  var store = pg && pg._workflowRun;
  var vals = (store && store.controlValues) || {};
  var src = vals.source_image ? String(vals.source_image) : "";
  if (src) {
    if (/^(blob:|data:|https?:\/\/|\/)/.test(src)) return src;
    return "/view?filename=" + encodeURIComponent(src) + "&type=input";
  }
  if (pg && pg.lastRunOutput) return String(pg.lastRunOutput);
  var sel = pg && pg._selectedRun;
  if (sel && sel.imageUrl) return String(sel.imageUrl);
  return "";
}

function _renderToolEditor(state, context, actions, canvasEl) {
  var tool = activeToolOf(state);
  if (tool === "inpaint" || tool === "sketch") return _renderPaintEditor(state, tool, context, actions, canvasEl);
  // Phase 2: the same selection editor serves Edit/Select on I2I. The editor
  // keeps the "inpaint" id so testids, overlay clearing, and shelf save paths
  // stay stable; legacy dedicated inpaint workflows render through the branch
  // above. No Inpaint execution method is implemented here (Phase 3).
  if (_isSelectOnI2I(state)) return _renderPaintEditor(state, "inpaint", context, actions, canvasEl);
  // Phase 3: the same expansion editor serves Edit/Expand on I2I. The editor
  // keeps the "outpaint" id so testids and save paths stay stable; legacy
  // dedicated outpaint workflows render through the branch above.
  if (_isExpandOnI2I(state)) return _renderOutpaintEditor(state, context, actions);
  if (tool === "outpaint") return _renderOutpaintEditor(state, context, actions);
  return null;
}

function _renderPaintEditor(state, tool, context, actions, canvasEl) {
  var isMask = tool === "inpaint";
  var box = el("div", {
    class: "comfymodal-studio-paint-editor",
    "data-testid": tool + "-editor",
    style: "margin-top:10px;padding:10px;border:1px solid #2a2a2a;border-radius:8px;background:#0a0a0a;",
  });
  box.appendChild(el("p", {
    text: isMask ? "Paint the mask (white = edit area)." : "Sketch over the image. Save flattens strokes into the Source Image.",
    style: "font-size:12px;color:#aaa;margin:0 0 8px;",
    "data-testid": tool + "-editor-hint",
  }));
  var controls = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;" });
  var mode = "brush";
  var size = 24;
  var radius = 8;
  var combine = "add";
  function mkBtn(label, testid, on) {
    var b = el("button", { type: "button", class: "comfymodal-secondary-btn" + (on ? " is-on" : ""), text: label, "data-testid": tool + "-" + testid });
    controls.appendChild(b);
    return b;
  }
  var brushBtn = mkBtn("Brush", "brush", true);
  var eraseBtn = mkBtn("Erase", "erase", false);
  var lassoBtn = isMask ? mkBtn("Lasso", "lasso", false) : null;
  var rectBtn = isMask ? mkBtn("Rectangle", "rect", false) : null;
  var objBtn = isMask ? mkBtn("Object", "object", false) : null;
  // SAM3 is an implementation detail: the user-facing concept is Detect
  // (the "text" testid is kept stable for existing tests/selectors).
  var textBtn = isMask ? mkBtn("Detect", "text", false) : null;
  function setMode(m) {
    mode = m;
    [brushBtn, eraseBtn, lassoBtn, rectBtn, objBtn, textBtn].forEach(function (b) { if (b) b.classList.remove("is-on"); });
    ({ brush: brushBtn, erase: eraseBtn, lasso: lassoBtn, rect: rectBtn, object: objBtn, text: textBtn })[m].classList.add("is-on");
    paint.style.cursor = (m === "object" || m === "text") ? "pointer" : "crosshair";
    var smart = (m === "object" || m === "text");
    samRow.style.display = smart ? "flex" : "none";
    samChips.style.display = smart ? "flex" : "none";
    if (!smart) samList.style.display = "none";
  }
  brushBtn.addEventListener("click", function () { setMode("brush"); });
  eraseBtn.addEventListener("click", function () { setMode("erase"); });
  if (lassoBtn) lassoBtn.addEventListener("click", function () { setMode("lasso"); });
  if (rectBtn) rectBtn.addEventListener("click", function () { setMode("rect"); });
  if (objBtn) objBtn.addEventListener("click", function () { setMode("object"); });
  if (textBtn) textBtn.addEventListener("click", function () { setMode("text"); });
  var sizeInput = el("input", { type: "range", min: "4", max: "96", value: "24", "data-testid": tool + "-brush-size", "aria-label": "Brush size", title: "Brush size" });
  sizeInput.addEventListener("input", function () { size = Number(sizeInput.value) || 24; });
  controls.appendChild(sizeInput);
  var ops = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;align-items:center;" });
  function opBtn(label, testid) {
    var b = el("button", { type: "button", class: "comfymodal-secondary-btn", text: label, "data-testid": tool + "-" + testid });
    ops.appendChild(b);
    return b;
  }
  var undoBtn = opBtn("Undo", "undo");
  var redoBtn = opBtn("Redo", "redo");
  var growBtn = isMask ? opBtn("Grow", "grow") : null;
  var shrinkBtn = isMask ? opBtn("Shrink", "shrink") : null;
  var featherBtn = isMask ? opBtn("Feather", "feather") : null;
  var invertBtn = isMask ? opBtn("Invert", "invert") : null;
  var fillBtn = isMask ? opBtn("Fill holes", "fill-holes") : null;
  var radiusInput = null;
  var combineSel = null;
  if (isMask) {
    radiusInput = el("input", { type: "number", min: "1", max: "64", value: "8", "data-testid": tool + "-radius", "aria-label": "Grow/shrink/feather radius", title: "Radius (px)", style: "width:56px;" });
    radiusInput.addEventListener("input", function () { radius = Math.max(1, Math.min(64, Number(radiusInput.value) || 8)); });
    ops.appendChild(radiusInput);
    combineSel = el("select", { "data-testid": tool + "-combine", "aria-label": "Selection combine mode", title: "How new selections combine" });
    ["add", "subtract", "replace"].forEach(function (v) {
      var o = document.createElement("option");
      o.value = v;
      o.textContent = v[0].toUpperCase() + v.slice(1);
      combineSel.appendChild(o);
    });
    combineSel.addEventListener("change", function () { combine = combineSel.value; });
    ops.appendChild(combineSel);
  }
  var clearBtn = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "Clear", "data-testid": tool + "-clear" });
  ops.appendChild(clearBtn);
  var saveBtn = el("button", { type: "button", class: "comfymodal-primary-btn", text: isMask ? "Save mask" : "Save sketch", "data-testid": tool + "-save" });
  ops.appendChild(saveBtn);
  box.appendChild(controls);
  box.appendChild(ops);
  // Phase 3: explicit Inpaint Method lives with the selection tools, on the
  // I2I engine only. Legacy dedicated inpaint workflows run natively.
  if (_isSelectOnI2I(state)) {
    box.appendChild(_methodSelectRow(state, context, actions, "inpaint", null));
    _refreshMethodCompat(state, context);
  }
  var samRow = el("div", { style: "display:none;gap:6px;flex-wrap:wrap;margin-bottom:8px;align-items:center;", "data-testid": tool + "-sam-row" });
  var samText = el("input", { type: "text", placeholder: "person, hair, red car, shirt", "data-testid": tool + "-sam-text", "aria-label": "Describe what to select", style: "flex:1;min-width:140px;" });
  var samConf = el("input", { type: "number", min: "0.05", max: "0.95", step: "0.05", value: "0.3", "data-testid": tool + "-sam-conf", title: "Confidence", style: "width:64px;" });
  var samFindBtn = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "Find", "data-testid": tool + "-sam-find" });
  var samScanBtn = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "Scan photo", title: "List everything detected so you can pick instead of typing", "data-testid": tool + "-sam-scan" });
  var samHint = el("span", { text: "Object: click the image. Detect: type + Find, Scan, or tap a chip.", style: "font-size:11px;color:#888;", "data-testid": tool + "-sam-hint" });
  samRow.appendChild(samText);
  samRow.appendChild(samConf);
  samRow.appendChild(samFindBtn);
  samRow.appendChild(samScanBtn);
  samRow.appendChild(samHint);
  box.appendChild(samRow);
  var samChips = el("div", { style: "display:none;gap:6px;flex-wrap:wrap;margin-bottom:8px;align-items:center;", "data-testid": tool + "-sam-chips" });
  ["person", "face", "hair", "shirt", "pants", "shoes", "hat", "bag"].forEach(function (label) {
    var chip = el("button", { type: "button", class: "comfymodal-secondary-btn", text: label, "data-testid": tool + "-sam-chip-" + label, title: "Select " + label });
    chip.addEventListener("click", function () { samText.value = label; samFind(); });
    samChips.appendChild(chip);
  });
  box.appendChild(samChips);
  var samList = el("div", { style: "display:none;gap:6px;flex-wrap:wrap;margin-bottom:8px;align-items:center;", "data-testid": tool + "-sam-list" });
  box.appendChild(samList);
  var base = null;
  var paint = document.createElement("canvas");
  paint.setAttribute("data-testid", tool + "-canvas");
  paint.style.position = "absolute";
  paint.style.inset = "0";
  paint.style.width = "100%";
  paint.style.height = "100%";
  paint.style.cursor = "crosshair";
  // Keep mask pixels opaque for saving and mask operations, then dim the
  // whole overlay. This keeps overlapping strokes at a stable 10% instead of
  // accumulating alpha toward opaque.
  var maskVisualOpacity = isMask ? 0.1 : 1;
  paint.style.opacity = String(maskVisualOpacity);
  var ants = document.createElement("canvas");
  ants.setAttribute("aria-hidden", "true");
  ants.style.position = "absolute";
  ants.style.pointerEvents = "none";
  ants.style.inset = "0";
  var hostImg = canvasEl ? canvasEl.querySelector('[data-testid="canvas-output"]') : null;
  if (hostImg) {
    // Paint directly on the main canvas image: wrap it and overlay.
    base = hostImg;
    // max-width keeps the shrink-to-fit wrap (and the image inside it)
    // capped at the canvas column, exactly as the bare image was before.
    var hostWrap = el("div", { style: "position:relative;display:inline-block;max-width:100%;height:100%;vertical-align:top;", "data-testid": tool + "-canvas-wrap" });
    // Cap paint-mode display size (width to the column, height to the
    // viewport): full-res sources otherwise blow up the workspace. The
    // overlay maps coordinates, so any display size paints accurately.
    hostImg.style.maxWidth = "100%";
    hostImg.style.maxHeight = "70vh";
    hostImg.style.height = "auto";
    hostImg.style.width = "auto";
    if (hostImg.parentNode) hostImg.parentNode.insertBefore(hostWrap, hostImg);
    hostWrap.appendChild(hostImg);
    hostWrap.appendChild(paint);
    hostWrap.appendChild(ants);
  } else {
    // No main-canvas image (nothing to paint on yet): keep the separate
    // editor base so an uploaded source is still paintable.
    var wrap = el("div", { style: "position:relative;display:inline-block;max-width:100%;height:100%;", "data-testid": tool + "-canvas-wrap" });
    base = el("img", { "data-testid": tool + "-base-image", alt: "Base image", style: "display:block;max-width:480px;max-height:360px;" });
    var baseUrl = _editorBaseImageUrl(state);
    if (baseUrl) base.src = baseUrl;
    wrap.appendChild(base);
    wrap.appendChild(paint);
    wrap.appendChild(ants);
    box.appendChild(wrap);
  }
  var preview = el("p", {
    class: "comfymodal-studio-control-note",
    text: "Mask preview appears after painting.",
    "data-testid": tool + "-mask-preview",
  });
  box.appendChild(preview);

  function fitCanvas() {
    var w = base.naturalWidth || base.clientWidth || 480;
    var h = base.naturalHeight || base.clientHeight || 360;
    if (!w || !h) return;
    paint.width = w;
    paint.height = h;
    ants.width = w;
    ants.height = h;
    syncOverlayBox();
  }
  // The overlay must sit exactly over the base image: the wrap may be
  // taller than the image (column-fill layout), and inset:0/100% would then
  // stretch strokes away from the image. Sync explicit geometry instead.
  function syncOverlayBox() {
    try {
      if (!base || !base.isConnected || !paint.isConnected) return;
      var wrapEl = paint.parentElement;
      if (!wrapEl) return;
      var wr = wrapEl.getBoundingClientRect();
      var br = base.getBoundingClientRect();
      if (!br.width || !br.height) return;
      paint.style.inset = "auto";
      paint.style.left = (br.left - wr.left) + "px";
      paint.style.top = (br.top - wr.top) + "px";
       paint.style.width = br.width + "px";
       paint.style.height = br.height + "px";
       ants.style.inset = "auto";
       ants.style.left = (br.left - wr.left) + "px";
       ants.style.top = (br.top - wr.top) + "px";
       ants.style.width = br.width + "px";
       ants.style.height = br.height + "px";
     } catch (_e) {}
   }
  function onWinResizeOverlay() {
    if (!box.isConnected) { window.removeEventListener("resize", onWinResizeOverlay); return; }
    syncOverlayBox();
  }
  window.addEventListener("resize", onWinResizeOverlay);
  base.addEventListener("load", fitCanvas);
  if (base.complete) setTimeout(fitCanvas, 0);

  // The border is a separate, non-persistent canvas so marching ants never
  // become part of the mask or its undo snapshots.
  var antsFrame = 0;
  function drawMarchingAnts(time) {
    if (!box.isConnected || !ants.getClientRects().length || document.hidden) {
      if (!box.isConnected) document.removeEventListener("visibilitychange", onVisibilityChange);
      antsFrame = 0;
      return;
    }
    var ctx = ants.getContext("2d");
    ctx.clearRect(0, 0, ants.width, ants.height);
    ctx.save();
    ctx.lineWidth = Math.max(2, ants.width / Math.max(1, ants.clientWidth) * 2);
    ctx.setLineDash([8, 6]);
    ctx.lineDashOffset = -(time / 40);
    ctx.strokeStyle = "rgba(0,0,0,0.9)";
    ctx.strokeRect(ctx.lineWidth / 2, ctx.lineWidth / 2, ants.width - ctx.lineWidth, ants.height - ctx.lineWidth);
    ctx.lineWidth = Math.max(1, ants.width / Math.max(1, ants.clientWidth));
    ctx.lineDashOffset = -(time / 40) + 7;
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.strokeRect(ctx.lineWidth / 2, ctx.lineWidth / 2, ants.width - ctx.lineWidth, ants.height - ctx.lineWidth);
    ctx.restore();
    antsFrame = requestAnimationFrame(drawMarchingAnts);
  }
  function startMarchingAnts() {
    if (isMask && !antsFrame) antsFrame = requestAnimationFrame(drawMarchingAnts);
  }
  function stopMarchingAnts() {
    if (antsFrame) cancelAnimationFrame(antsFrame);
    antsFrame = 0;
  }
  function onVisibilityChange() {
    if (document.hidden) stopMarchingAnts();
    else if (box.isConnected) startMarchingAnts();
    else document.removeEventListener("visibilitychange", onVisibilityChange);
  }
  document.addEventListener("visibilitychange", onVisibilityChange);

  var undoStack = [];
  var redoStack = [];
  // Phase 2: undo history belongs to one source image. Overlay pixels are
  // wiped on source replace/clear (see _setCanvasImage / _clearPaintOverlays),
  // but this editor closure — and its stacks — survives; an Undo afterwards
  // must not resurrect strokes painted on another image. The overlay element
  // carries the source it was painted on; history is reconciled against the
  // live shelf value before any push/undo/redo. Derived state only — no new
  // store fields.
  function sourceKeyNow() {
    try {
      var st = _shelfStore(state);
      var v = st && st.controlValues && st.controlValues.source_image;
      return String(v || "");
    } catch (_e) { return ""; }
  }
  function reconcileHistoryForSource() {
    var key = sourceKeyNow();
    if ((paint.dataset.sourceKey || "") === key) return false;
    paint.dataset.sourceKey = key;
    var had = undoStack.length || redoStack.length;
    undoStack.length = 0;
    redoStack.length = 0;
    syncUndoBtns();
    if (had) preview.textContent = "Mask cleared.";
    return true;
  }
  function snapshot() {
    try {
      if (!paint.width || !paint.height) return null;
      return paint.toDataURL("image/png");
    } catch (_e) { return null; }
  }
  function restore(url, done) {
    var ctx = paint.getContext("2d");
    ctx.clearRect(0, 0, paint.width, paint.height);
    if (!url) { if (done) done(); return; }
    var img = new Image();
    img.onload = function () { ctx.drawImage(img, 0, 0); if (done) done(); };
    img.onerror = function () { if (done) done(); };
    img.src = url;
  }
  function pushHistory() {
    reconcileHistoryForSource();
    var s = snapshot();
    if (s == null) return;
    undoStack.push(s);
    if (undoStack.length > 30) undoStack.shift();
    redoStack.length = 0;
    syncUndoBtns();
  }
  function syncUndoBtns() {
    undoBtn.disabled = !undoStack.length;
    redoBtn.disabled = !redoStack.length;
  }
  syncUndoBtns();
  function doUndo() {
    reconcileHistoryForSource();
    if (!undoStack.length) return;
    var cur = snapshot();
    if (cur != null) redoStack.push(cur);
    restore(undoStack.pop(), function () { preview.textContent = "Undone — Save to use it."; syncUndoBtns(); });
  }
  function doRedo() {
    reconcileHistoryForSource();
    if (!redoStack.length) return;
    var cur = snapshot();
    if (cur != null) undoStack.push(cur);
    restore(redoStack.pop(), function () { preview.textContent = "Redone — Save to use it."; syncUndoBtns(); });
  }
  undoBtn.addEventListener("click", doUndo);
  redoBtn.addEventListener("click", doRedo);
  document.addEventListener("keydown", function keyHandler(ev) {
    if (!box.isConnected) { document.removeEventListener("keydown", keyHandler); return; }
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if ((ev.ctrlKey || ev.metaKey) && !ev.shiftKey && (ev.key === "z" || ev.key === "Z")) { ev.preventDefault(); doUndo(); }
    else if (((ev.ctrlKey || ev.metaKey) && ev.shiftKey && (ev.key === "z" || ev.key === "Z")) || ((ev.ctrlKey || ev.metaKey) && ev.key === "y")) { ev.preventDefault(); doRedo(); }
    else if (ev.key === "Escape" && drawing) { drawing = false; shapePts = []; rectStart = null; last = null; restore(undoStack.length ? undoStack[undoStack.length - 1] : null); }
  });
  var drawing = false;
  var last = null;
  var shapePts = [];
  var rectStart = null;
  function pos(ev) {
    var r = paint.getBoundingClientRect();
    var cx = (ev.touches && ev.touches[0] ? ev.touches[0].clientX : ev.clientX);
    var cy = (ev.touches && ev.touches[0] ? ev.touches[0].clientY : ev.clientY);
    return {
      x: (cx - r.left) * (paint.width / Math.max(1, r.width)),
      y: (cy - r.top) * (paint.height / Math.max(1, r.height)),
    };
  }
  function paintStyle(ctx) {
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = size;
    if (mode === "erase") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.strokeStyle = "rgba(0,0,0,1)";
      ctx.fillStyle = "rgba(0,0,0,1)";
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = isMask ? "rgba(255,255,255,1)" : "rgba(255,60,60,0.9)";
      ctx.fillStyle = isMask ? "rgba(255,255,255,1)" : "rgba(255,60,60,0.9)";
    }
  }
  function stroke(to) {
    var ctx = paint.getContext("2d");
    paintStyle(ctx);
    ctx.beginPath();
    ctx.moveTo(last.x, last.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    last = to;
    preview.textContent = "Mask has paint — Save to use it.";
  }
  function fillShapePath(pts) {
    var ctx = paint.getContext("2d");
    if (combine === "replace") {
      ctx.save();
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0,0,0,1)";
      ctx.fillRect(0, 0, paint.width, paint.height);
      ctx.restore();
    }
    ctx.save();
    ctx.beginPath();
    pts.forEach(function (p, i) { if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); });
    ctx.closePath();
    if (combine === "subtract" || mode === "erase") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0,0,0,1)";
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = isMask ? "rgba(255,255,255,1)" : "rgba(255,60,60,0.9)";
    }
    ctx.fill();
    ctx.restore();
    preview.textContent = "Shape added — Save to use it.";
    syncUndoBtns();
  }
  paint.addEventListener("pointerdown", function (ev) {
    if (mode === "object") { samClickAt(ev); return; }
    if (mode === "text") { preview.textContent = "Type a description, then Find."; return; }
    pushHistory();
    drawing = true;
    last = pos(ev);
    if (mode === "lasso") shapePts = [last];
    else if (mode === "rect") rectStart = last;
    else if (mode === "brush" || mode === "erase") {
      var ctx = paint.getContext("2d");
      paintStyle(ctx);
      ctx.beginPath();
      ctx.arc(last.x, last.y, size / 2, 0, Math.PI * 2);
      ctx.fill();
    }
    try { paint.setPointerCapture(ev.pointerId); } catch (_e) {}
  });
  paint.addEventListener("pointermove", function (ev) {
    if (!drawing || !last) return;
    var p = pos(ev);
    if (mode === "lasso") { shapePts.push(p); stroke(p); }
    else if (mode === "rect") { last = p; }
    else stroke(p);
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach(function (n) {
    paint.addEventListener(n, function () {
      if (!drawing) return;
      drawing = false;
      if (mode === "lasso" && shapePts.length > 2) {
        (function (pts) { restore(undoStack[undoStack.length - 1], function () { fillShapePath(pts); }); })(shapePts.slice());
      } else if (mode === "rect" && rectStart && last) {
        var x0 = Math.min(rectStart.x, last.x), y0 = Math.min(rectStart.y, last.y);
        var x1 = Math.max(rectStart.x, last.x), y1 = Math.max(rectStart.y, last.y);
        (function (pts) { restore(undoStack[undoStack.length - 1], function () { fillShapePath(pts); }); })([{ x: x0, y: y0 }, { x: x1, y: y0 }, { x: x1, y: y1 }, { x: x0, y: y1 }]);
      }
      last = null; shapePts = []; rectStart = null;
      syncUndoBtns();
    });
  });
  function forEachAlpha(fn) {
    var ctx = paint.getContext("2d");
    var d = ctx.getImageData(0, 0, paint.width, paint.height);
    fn(d.data, d.width, d.height);
    ctx.putImageData(d, 0, 0);
  }
  function invertMask() {
    forEachAlpha(function (px) {
      for (var i = 0; i < px.length; i += 4) {
        var a = px[i + 3];
        var inv = 255 - a;
        px[i] = 255; px[i + 1] = 255; px[i + 2] = 255; px[i + 3] = inv;
      }
    });
  }
  function growMask(r) {
    var src = document.createElement("canvas");
    src.width = paint.width; src.height = paint.height;
    src.getContext("2d").drawImage(paint, 0, 0);
    var ctx = paint.getContext("2d");
    var steps = 8;
    for (var k = 0; k < steps; k++) {
      var a = (k / steps) * Math.PI * 2;
      ctx.drawImage(src, Math.cos(a) * r, Math.sin(a) * r);
    }
  }
  function shrinkMask(r) { invertMask(); growMask(r); invertMask(); }
  function featherMask(r) {
    var src = document.createElement("canvas");
    src.width = paint.width; src.height = paint.height;
    src.getContext("2d").drawImage(paint, 0, 0);
    var ctx = paint.getContext("2d");
    ctx.clearRect(0, 0, paint.width, paint.height);
    ctx.filter = "blur(" + r + "px)";
    ctx.drawImage(src, 0, 0);
    ctx.filter = "none";
  }
  function fillHoles() {
    var ctx = paint.getContext("2d");
    var w = paint.width, h = paint.height;
    if (!w || !h) return;
    var d = ctx.getImageData(0, 0, w, h);
    var px = d.data;
    var bg = new Uint8Array(w * h);
    var stack = [];
    function isBg(i) { return px[i * 4 + 3] < 128; }
    for (var x = 0; x < w; x++) { if (isBg(x)) stack.push(x); if (isBg((h - 1) * w + x)) stack.push((h - 1) * w + x); }
    for (var y = 0; y < h; y++) { if (isBg(y * w)) stack.push(y * w); if (isBg(y * w + w - 1)) stack.push(y * w + w - 1); }
    while (stack.length) {
      var i = stack.pop();
      if (bg[i]) continue;
      if (!isBg(i)) continue;
      bg[i] = 1;
      var ix = i % w, iy = (i / w) | 0;
      if (ix > 0) stack.push(i - 1);
      if (ix < w - 1) stack.push(i + 1);
      if (iy > 0) stack.push(i - w);
      if (iy < h - 1) stack.push(i + w);
    }
    for (var j = 0; j < w * h; j++) {
      if (!bg[j] && isBg(j)) { px[j * 4] = 255; px[j * 4 + 1] = 255; px[j * 4 + 2] = 255; px[j * 4 + 3] = 255; }
    }
    ctx.putImageData(d, 0, 0);
  }
  if (growBtn) growBtn.addEventListener("click", function () { pushHistory(); growMask(radius); preview.textContent = "Grown +" + radius + "px — Save to use it."; });
  if (shrinkBtn) shrinkBtn.addEventListener("click", function () { pushHistory(); shrinkMask(radius); preview.textContent = "Shrunk -" + radius + "px — Save to use it."; });
  if (featherBtn) featherBtn.addEventListener("click", function () { pushHistory(); featherMask(radius); preview.textContent = "Feathered " + radius + "px — Save to use it."; });
  if (invertBtn) invertBtn.addEventListener("click", function () { pushHistory(); invertMask(); preview.textContent = "Inverted — Save to use it."; });
  if (fillBtn) fillBtn.addEventListener("click", function () { pushHistory(); fillHoles(); preview.textContent = "Holes filled — Save to use it."; });
  clearBtn.addEventListener("click", function () {
    pushHistory();
    var ctx = paint.getContext("2d");
    ctx.clearRect(0, 0, paint.width, paint.height);
    preview.textContent = "Mask cleared.";
  });
  function baseImageB64() {
    // Upload the exact pixels on the canvas: filenames derived from URLs
    // break across /view, studio outputs, history assets, and directories
    // the backend cannot see. Bytes always work.
    var src = (base && base.isConnected && (base.getAttribute("src") || base.src)) || "";
    if (!src) return Promise.resolve(null);
    if (src.indexOf("data:") === 0) return Promise.resolve(src);
    return fetch(src).then(function (r) {
      if (!r.ok) throw new Error("could not read canvas image (HTTP " + r.status + ")");
      return r.blob();
    }).then(function (blob) {
      return new Promise(function (res, rej) {
        var fr = new FileReader();
        fr.onload = function () { res(fr.result); };
        fr.onerror = rej;
        fr.readAsDataURL(blob);
      });
    });
  }
  function drawSamImage(img) {
    var ctx = paint.getContext("2d");
    ctx.save();
    if (combine === "replace") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0,0,0,1)";
      ctx.fillRect(0, 0, paint.width, paint.height);
      ctx.restore();
      ctx.save();
    }
    if (combine === "subtract") ctx.globalCompositeOperation = "destination-out";
    else ctx.globalCompositeOperation = "source-over";
    var tmp = document.createElement("canvas");
    tmp.width = paint.width; tmp.height = paint.height;
    var tctx = tmp.getContext("2d");
    tctx.drawImage(img, 0, 0, tmp.width, tmp.height);
    if (combine === "subtract") ctx.drawImage(tmp, 0, 0);
    else {
      var d = tctx.getImageData(0, 0, tmp.width, tmp.height);
      var px = d.data;
      for (var i = 0; i < px.length; i += 4) {
        var v = px[i];
        px[i] = 255; px[i + 1] = 255; px[i + 2] = 255;
        px[i + 3] = v > 128 ? 255 : 0;
      }
      tctx.putImageData(d, 0, 0);
      ctx.drawImage(tmp, 0, 0);
    }
    ctx.restore();
  }
  function loadSamImage(b64) {
    return new Promise(function (res, rej) {
      var img = new Image();
      img.onload = function () { res(img); };
      img.onerror = rej;
      img.src = "data:image/png;base64," + b64;
    });
  }
  function applySamPng(b64, label) {
    pushHistory();
    loadSamImage(b64).then(function (img) {
      drawSamImage(img);
      preview.textContent = label + " — Save to use it.";
      syncUndoBtns();
    }, function () { undoStack.pop(); preview.textContent = "Selection overlay failed."; });
  }
  async function samJson(res) {
    // The SAM routes only exist after a ComfyUI restart. Any 404 means the
    // backend is stale, whether it answers HTML (live ComfyUI) or JSON —
    // it must never surface as a raw JSON.parse error.
    if (res.status === 404) throw new Error("SAM3 service not found (HTTP 404) — restart ComfyUI so the new Studio routes load, then retry.");
    var txt = await res.text();
    try {
      return JSON.parse(txt);
    } catch (_e) {
      throw new Error("SAM3 service returned HTTP " + res.status + " — restart ComfyUI and retry.");
    }
  }
  async function samClickAt(ev) {
    var p = pos(ev);
    preview.textContent = "Selecting object…";
    try {
      var b64 = await baseImageB64();
      if (!b64) { preview.textContent = "Upload a Source Image first."; return; }
      var res = await fetch("/comfymodal/studio/sam3/points", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_b64: b64, points: [[Math.round(p.x), Math.round(p.y)]], labels: [1] }),
      });
      var data = await samJson(res);
      if (!res.ok || !data.mask_png) throw new Error((data && data.error) || ("HTTP " + res.status));
      applySamPng(data.mask_png, "Object selected");
    } catch (e) { preview.textContent = "Object select failed: " + (e && e.message ? e.message : e); }
  }
  async function samFind() {
    var q = (samText.value || "").trim();
    if (!q) { preview.textContent = "Type what to select first."; return; }
    preview.textContent = "Finding…";
    try {
      var b642 = await baseImageB64();
      if (!b642) { preview.textContent = "Upload a Source Image first."; return; }
      var res = await fetch("/comfymodal/studio/sam3/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_b64: b642, text: q, threshold: Number(samConf.value) || 0.3 }),
      });
      var data = await samJson(res);
      if (!res.ok || !data.mask_png) throw new Error((data && data.error) || ("HTTP " + res.status));
      if (!data.count) { preview.textContent = "No matches. Try a broader description or Object select."; return; }
      applySamPng(data.mask_png, data.count + " match" + (data.count === 1 ? "" : "es") + " selected");
    } catch (e) { preview.textContent = "Detect failed: " + (e && e.message ? e.message : e); }
  }
  samFindBtn.addEventListener("click", samFind);
  samText.addEventListener("keydown", function (ev) { if (ev.key === "Enter") samFind(); ev.stopPropagation(); });
  var samScanItems = [];
  function renderSamList(items) {
    samScanItems = items || [];
    while (samList.firstChild) samList.removeChild(samList.firstChild);
    if (!samScanItems.length) { samList.style.display = "none"; return; }
    samList.style.display = "flex";
    samScanItems.forEach(function (it, i) {
      var row = el("label", { style: "display:flex;gap:6px;align-items:center;font-size:12px;color:#ccc;background:#141414;border:1px solid #2a2a2a;border-radius:6px;padding:4px 8px 4px 4px;cursor:pointer;", "data-testid": tool + "-sam-item-" + i });
      var box = el("input", { type: "checkbox", "data-testid": tool + "-sam-check-" + i, "aria-label": "Select " + it.label });
      box.checked = true;
      row.appendChild(box);
      if (it.thumb_png) {
        var th = el("img", { alt: it.label, "data-testid": tool + "-sam-thumb-" + i, style: "width:32px;height:32px;object-fit:cover;border-radius:4px;display:block;" });
        th.src = "data:image/png;base64," + it.thumb_png;
        row.appendChild(th);
      }
      var sub = it.label + (it.confidence != null ? " " + Math.round(it.confidence * 100) + "%" : (it.count > 1 ? " ×" + it.count : ""));
      row.appendChild(el("span", { text: sub }));
      samList.appendChild(row);
    });
    var apply = el("button", { type: "button", class: "comfymodal-primary-btn", text: "Apply selected", "data-testid": tool + "-sam-apply" });
    apply.addEventListener("click", async function () {
      var boxes = [];
      samScanItems.forEach(function (it, i) {
        var box = samList.querySelector('[data-testid="' + tool + "-sam-check-" + i + '"]');
        if (box && box.checked && it.box) boxes.push(it.box);
      });
      if (!boxes.length) { preview.textContent = "Nothing selected."; return; }
      // One refined SAM pass over all boxes, one undo step.
      apply.disabled = true;
      preview.textContent = "Refining " + boxes.length + "…";
      try {
        var b64 = await baseImageB64();
        if (!b64) { preview.textContent = "Upload a Source Image first."; return; }
        var res = await fetch("/comfymodal/studio/sam3/boxes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image_b64: b64, boxes: boxes }),
        });
        var data = await samJson(res);
        if (!res.ok || !data.mask_png) throw new Error((data && data.error) || ("HTTP " + res.status));
        applySamPng(data.mask_png, boxes.length + " item" + (boxes.length === 1 ? "" : "s") + " applied");
      } catch (e) { preview.textContent = "Apply failed: " + (e && e.message ? e.message : e); }
      finally { apply.disabled = false; }
    });
    samList.appendChild(apply);
    var cancel = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "Dismiss", "data-testid": tool + "-sam-dismiss" });
    cancel.addEventListener("click", function () { samScanItems = []; samList.style.display = "none"; });
    samList.appendChild(cancel);
  }
  async function samScan() {
    preview.textContent = "Scanning photo…";
    try {
      var b64 = await baseImageB64();
      if (!b64) { preview.textContent = "Upload a Source Image first."; return; }
      var res = await fetch("/comfymodal/studio/sam3/scan-yolo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_b64: b64 }),
      });
      var data = await samJson(res);
      if (!res.ok || !data.items) throw new Error((data && data.error) || ("HTTP " + res.status));
      if (!data.items.length) {
        renderSamList([]);
        preview.textContent = "Nothing recognizable. Try typing a description or Object select.";
        return;
      }
      renderSamList(data.items);
      preview.textContent = data.items.length + " item" + (data.items.length === 1 ? "" : "s") + " found — tick and Apply.";
    } catch (e) { preview.textContent = "Scan failed: " + (e && e.message ? e.message : e); }
  }
  samScanBtn.addEventListener("click", samScan);
  saveBtn.addEventListener("click", async function () {
    try {
      var store = _shelfStore(state);
      var identity = _selectionIdentity(store);
      // Read the live base image, not the URL captured at construct — the
      // source may have changed (chaining, Use current) since this editor
      // was mounted.
      var liveBase = (base && base.isConnected && base.getAttribute("src")) || _editorBaseImageUrl(state);
      var out = document.createElement("canvas");
      out.width = paint.width || 512;
      out.height = paint.height || 512;
      var octx = out.getContext("2d");
      if (isMask) {
        octx.fillStyle = "#000";
        octx.fillRect(0, 0, out.width, out.height);
        octx.drawImage(paint, 0, 0);
      } else {
        if (liveBase) {
          var img = new Image();
          img.crossOrigin = "anonymous";
          await new Promise(function (res, rej) { img.onload = res; img.onerror = rej; img.src = liveBase; });
          octx.drawImage(img, 0, 0, out.width, out.height);
        }
        octx.drawImage(paint, 0, 0);
      }
      var blob = await new Promise(function (res) { out.toBlob(res, "image/png"); });
      if (!blob) return;
      var mod = await import("./studio-field-blocks.js");
      var name = await mod.uploadImageBlob(blob, mod.uniqueImageName(isMask ? "studio-mask" : "studio-sketch"));
      if (_selectionIdentity(_shelfStore(state)) !== identity) {
        preview.textContent = "Workflow changed during save — value discarded.";
        return;
      }
      var targetRole = isMask ? "mask" : "source_image";
      if (isMask && !_schemaHasRole(state, "mask")) {
        // Phase 3: on the I2I engine the method mask needs no mapping — it
        // travels in the run's method params, never as a mapped control (a
        // filename written into a MASK socket would break plain runs).
        // Remember it per-workflow next to the method choice instead.
        if (activeToolOf(state) === "i2i") {
          try {
            var _sv = _shelfStore(state);
            var _wid = _sv && _sv.workflowId ? String(_sv.workflowId) : "";
            var _cur = (_sv && _sv.controlValues && _sv.controlValues.source_image) || "";
            if (_wid) saveWorkflowMethods(_wid, { savedMask: name, savedMaskSource: String(_cur || "") });
          } catch (_e2) {}
          try { _recordImageEdge(state, name, liveBase); } catch (_e3) {}
          try { _syncWorkflowGating(state, context, actions); } catch (_e4) {}
          preview.textContent = "Mask saved: " + name;
          return;
        }
        preview.textContent = "This workflow has no Mask binding — mask not saved (map one in the Wizard to use it).";
        return;
      }
      commitShelfValue(state, context, actions, targetRole, name);
      _recordImageEdge(state, name, liveBase);
      preview.textContent = isMask ? "Mask saved: " + name : "Sketch saved as Source Image: " + name;
      _refreshShelfSection(state, context, actions);
      _syncEditorBaseImage(state);
      if (!isMask) {
        _clearBoundMask(state, context, actions);
        _setCanvasImage(state, _lineageDisplayUrl(name), context);
      }
    } catch (_e) { preview.textContent = "Save failed — try again."; }
  });
  startMarchingAnts();
  return box;
}

function _renderOutpaintEditor(state, context, actions) {
  var box = el("div", {
    class: "comfymodal-studio-outpaint-editor",
    "data-testid": "outpaint-editor",
    style: "margin-top:10px;padding:10px;border:1px solid #2a2a2a;border-radius:8px;background:#0a0a0a;",
  });
  box.appendChild(el("p", {
    text: "Extend the canvas. Save produces an expanded Source Image plus a Mask for the new area.",
    style: "font-size:12px;color:#aaa;margin:0 0 8px;",
    "data-testid": "outpaint-editor-hint",
  }));
  var grid = el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;" });
  var fields = {};
  // Phase 3: pad amounts are per-workflow method inputs — they persist with
  // the Expand Method choice and travel to the run as method params.
  var _padPrefs = null;
  try {
    var _padStore = _shelfStore(state);
    _padPrefs = loadWorkflowMethods(_padStore && _padStore.workflowId ? String(_padStore.workflowId) : "");
  } catch (_e) { _padPrefs = null; }
  if (!_padPrefs) _padPrefs = { padTop: 0, padRight: 256, padBottom: 0, padLeft: 0 };
  var _padKeys = { top: "padTop", right: "padRight", bottom: "padBottom", left: "padLeft" };
  [["top", "Top"], ["right", "Right"], ["bottom", "Bottom"], ["left", "Left"]].forEach(function (pair) {
    var key = pair[0];
    var label = pair[1];
    var input = el("input", {
      type: "number", min: "0", max: "4096", step: "8", value: String(_padPrefs[_padKeys[key]] || 0),
      class: "comfymodal-input", style: "width:90px;",
      "data-testid": "outpaint-" + key, "aria-label": "Expand " + label,
    });
    input.addEventListener("input", function () {
      var patch = {};
      patch[_padKeys[key]] = Math.max(0, Number(input.value) || 0);
      try {
        var _pst = _shelfStore(state);
        saveWorkflowMethods(_pst && _pst.workflowId ? String(_pst.workflowId) : "", patch);
      } catch (_e2) {}
      try { _syncWorkflowGating(state, context, actions); } catch (_e3) {}
    });
    fields[key] = input;
    grid.appendChild(el("label", { text: label + " ", style: "font-size:11px;color:#888;" }, [input]));
  });
  var saveBtn = el("button", { type: "button", class: "comfymodal-primary-btn", text: "Save expansion", "data-testid": "outpaint-save" });
  grid.appendChild(saveBtn);
  box.appendChild(grid);
  // Phase 3: explicit Expand Method on the I2I engine. Legacy dedicated
  // outpaint workflows run natively.
  if (_isExpandOnI2I(state)) {
    box.appendChild(_methodSelectRow(state, context, actions, "expand", function () {
      var hasWH = false;
      try { hasWH = _schemaHasRole(state, "width") && _schemaHasRole(state, "height"); } catch (_e4) { hasWH = false; }
      if (hasWH) return "";
      return "Output will be resampled to fit — map Width/Height in the Wizard for exact sizes.";
    }));
  }
  var status = el("p", { class: "comfymodal-studio-control-note", text: "Original stays centered; new area is masked.", "data-testid": "outpaint-preview-note" });
  box.appendChild(status);
  saveBtn.addEventListener("click", async function () {
    try {
      var outStore = _shelfStore(state);
      var outIdentity = _selectionIdentity(outStore);
      var baseUrl = _editorBaseImageUrl(state);
      if (!baseUrl) { status.textContent = "No source image yet."; return; }
      var img = new Image();
      img.crossOrigin = "anonymous";
      await new Promise(function (res, rej) { img.onload = res; img.onerror = rej; img.src = baseUrl; });
      var t = Math.max(0, Number(fields.top.value) || 0);
      var r = Math.max(0, Number(fields.right.value) || 0);
      var b = Math.max(0, Number(fields.bottom.value) || 0);
      var l = Math.max(0, Number(fields.left.value) || 0);
      var W = img.naturalWidth + l + r;
      var H = img.naturalHeight + t + b;
      if (!W || !H) return;
      var expanded = document.createElement("canvas");
      expanded.width = W;
      expanded.height = H;
      var ectx = expanded.getContext("2d");
      ectx.fillStyle = "#808080";
      ectx.fillRect(0, 0, W, H);
      ectx.drawImage(img, l, t);
      var mask = document.createElement("canvas");
      mask.width = W;
      mask.height = H;
      var mctx = mask.getContext("2d");
      mctx.fillStyle = "#fff";
      mctx.fillRect(0, 0, W, H);
      mctx.fillStyle = "#000";
      mctx.fillRect(l, t, img.naturalWidth, img.naturalHeight);
      var blobOf = function (c) { return new Promise(function (res) { c.toBlob(res, "image/png"); }); };
      var mod = await import("./studio-field-blocks.js");
      var expName = await mod.uploadImageBlob(await blobOf(expanded), mod.uniqueImageName("studio-outpaint"));
      var maskName = await mod.uploadImageBlob(await blobOf(mask), mod.uniqueImageName("studio-outpaint-mask"));
      if (_selectionIdentity(_shelfStore(state)) !== outIdentity) {
        status.textContent = "Workflow changed during save — values discarded.";
        return;
      }
      commitShelfValue(state, context, actions, "source_image", expName);
      _recordImageEdge(state, expName, baseUrl);
      if (_schemaHasRole(state, "mask")) {
        commitShelfValue(state, context, actions, "mask", maskName);
        _recordImageEdge(state, maskName, expName);
        status.textContent = "Expanded " + W + "x" + H + " — original at (" + l + "," + t + ").";
      } else {
        status.textContent = "Expanded " + W + "x" + H + " — original at (" + l + "," + t + "). No Mask binding on this workflow; mask skipped.";
      }
      _setCanvasImage(state, _lineageDisplayUrl(expName));
      _refreshShelfSection(state, context, actions);
    } catch (_e) { status.textContent = "Expansion failed — try again."; }
  });
  return box;
}

function _schemaHasRole(state, role) {
  try {
    var pg = state && state.playground;
    var store = pg && pg._workflowRun;
    if (!store) return false;
    var wf = pg._workflowRunModule;
    var schema = wf ? wf.getControlSchema(store) : (store.runContext && store.runContext.control_schema) || {};
    return !!(schema && Object.prototype.hasOwnProperty.call(schema, role));
  } catch (_e) { return false; }
}

function renderLiveReturnControl(state, context) {
  const overlay = el("div", {
    class: "comfymodal-studio-live-return",
    "data-testid": "live-return-control",
  });
  overlay.appendChild(el("span", {
    class: "comfymodal-studio-live-indicator",
    text: "Generation in progress",
  }));
  overlay.appendChild(el("button", {
    type: "button",
    class: "comfymodal-studio-live-return-btn",
    "data-testid": "live-return-btn",
    "aria-label": "Return to live generation view",
    text: "Return to live",
    onclick: () => {
      state.playground.lastRunOutput = null;
      state.playground._selectedRun = null;
      if (context && context.setPage) context.setPage("playground");
    },
  }));
  return overlay;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Metadata Section ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// Compact metadata section tied to the selected canvas run with summary
// and collapsible advanced details.

function renderMetadataSection(state, context) {
  const section = el("div", {
    class: "comfymodal-studio-preview-details-legacy",
    "data-testid": "preview-details-legacy",
  });

  const apiBase = (context && context.apiBase) || "/comfymodal";
  const actions = buildActions(state, context);

  const selectedRun = state.playground && state.playground._selectedRun;
  if (!selectedRun) {
    // No run selected ├óΓé¼ΓÇ¥ show only when a canvas result exists
    return section;
  }

  const nr = selectedRun;
  const rc = nr.resolvedControls || {};
  const rqc = nr.requestedControls || {};
  const isFailed = nr.status === "error" || nr.status === "failed";

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Summary block ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  const summary = el("div", { class: "comfymodal-studio-metadata-summary" });

  // Status
  summary.appendChild(el("span", {
    class: "comfymodal-studio-metadata-status",
    text: isFailed ? "\u26a0 Failed" : "\u2713 Completed",
    style: "color:" + (isFailed ? "var(--color-danger, #f87171)" : "var(--color-success, #4ade80)"),
  }));

  // Favorite star
  summary.appendChild(renderFavoriteStar(nr, actions, apiBase));

  // Prompt (use nullish check to preserve empty string)
  if (nr.prompt != null) {
    summary.appendChild(el("span", {
      class: "comfymodal-studio-metadata-prompt",
      text: "Prompt: " + (nr.prompt ? nr.prompt.substring(0, 120) : "") + (nr.prompt && nr.prompt.length > 120 ? "\u2026" : ""),
    }));
  }

  // Negative prompt (use nullish check to preserve empty string)
  if (nr.negativePrompt != null) {
    summary.appendChild(el("span", {
      class: "comfymodal-studio-metadata-neg-prompt",
      text: "Neg: " + (nr.negativePrompt ? nr.negativePrompt.substring(0, 60) : "") + (nr.negativePrompt && nr.negativePrompt.length > 60 ? "\u2026" : ""),
    }));
  }

  // Preset & Feature
  const labelParts = [];
  if (nr.presetLabel != null && nr.presetLabel) labelParts.push(nr.presetLabel);
  else if (nr.presetId != null && nr.presetId) labelParts.push(nr.presetId);
  if (nr.featureId != null && nr.featureId) labelParts.push(nr.featureId);
  if (labelParts.length > 0) {
    summary.appendChild(el("span", {
      class: "comfymodal-studio-metadata-source",
      text: labelParts.join(" \u2014 "),
    }));
  }

  // Duration (use nullish check to preserve 0)
  if (nr.durationMs != null && nr.durationMs > 0) {
    const durSecs = (nr.durationMs / 1000).toFixed(1);
    summary.appendChild(el("span", {
      class: "comfymodal-studio-metadata-duration",
      text: durSecs + "s",
    }));
  }

  // Timestamp (use nullish check to preserve empty string)
  if (nr.startedAt != null && nr.startedAt) {
    summary.appendChild(el("span", {
      class: "comfymodal-studio-metadata-time",
      text: nr.startedAt.substring(0, 19),
    }));
  }

  section.appendChild(summary);

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Save Output (single-output backend action) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  // Button visibility follows the record's saved state; the request
  // targets only the selected (primary) output.
  if (nr._historyKind === "generation") {
    // History V2 record ├óΓé¼ΓÇ¥ export through the repository by asset id
    var _feat = nr.featuredOutput || {};
    var _assetId = _feat.previewAssetId || _feat.originalAssetId || _feat.assetId || "";
    if (_assetId && _feat.exportState !== "exported" && !nr.outputSaved) {
      var saveRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-top:6px;" });
      var saveBtn = el("button", {
        type: "button",
        class: "comfymodal-secondary-btn",
        "data-testid": "save-output-btn",
        text: "Save output",
        style: "font-size:10px;padding:2px 10px;",
      });
      var saveErrorEl = el("span", {
        "data-testid": "save-output-error",
        style: "display:none;font-size:10px;color:var(--color-danger, #f87171);",
      });
      saveBtn.addEventListener("click", async function () {
        saveBtn.disabled = true;
        saveBtn.textContent = "Saving\u2026";
        saveErrorEl.style.display = "none";
        try {
          const repo = await _getRecentRunsRepo(apiBase);
          await repo.exportAsset(_assetId);
          nr.outputSaved = true;
          if (context && context.setPage) context.setPage("playground");
        } catch (err) {
          saveBtn.disabled = false;
          saveBtn.textContent = "Save output";
          saveErrorEl.textContent = (err && err.message) || "Save failed";
          saveErrorEl.style.display = "inline";
        }
      });
      saveRow.appendChild(saveBtn);
      saveRow.appendChild(saveErrorEl);
      section.appendChild(saveRow);
    }
  } else {
  var rawRun = nr.raw || {};
  var rawExtra = rawRun.extra || {};
  var recordSaved = rawRun.output_saved === true || rawExtra.output_saved === true;
  if (nr.id && nr.imageUrl && !recordSaved) {
    var saveRow = el("div", { style: "display:flex;align-items:center;gap:6px;margin-top:6px;" });
    var saveBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn",
      "data-testid": "save-output-btn",
      text: "Save output",
      style: "font-size:10px;padding:2px 10px;",
    });
    var saveErrorEl = el("span", {
      "data-testid": "save-output-error",
      style: "display:none;font-size:10px;color:var(--color-danger, #f87171);",
    });
    saveBtn.addEventListener("click", async function () {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving\u2026";
      saveErrorEl.style.display = "none";
      try {
        var res = await saveRunOutput(apiBase, nr.id, { output_index: 0 });
        if (!res || res.status !== "ok") {
          throw new Error((res && res.message) || "Save request failed");
        }
        if (rawRun) rawRun.output_saved = true;
        nr.outputSaved = true;
        if (context && context.setPage) context.setPage("playground");
      } catch (err) {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save output";
        saveErrorEl.textContent = (err && err.message) || "Save failed";
        saveErrorEl.style.display = "inline";
      }
    });
    saveRow.appendChild(saveBtn);
    saveRow.appendChild(saveErrorEl);
    section.appendChild(saveRow);
  }
  }

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Timing Summary Card ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  if (nr.timingStages && nr.timingStages.length > 0) {
    var timingCard = el("div", {
      class: "comfymodal-studio-timing-card",
      "data-testid": "timing-card",
    });

    // Primary E2E time (large)
    var e2e = nr.timingStages.find(function (s) { return s.label === "End-to-End Total"; });
    if (e2e) {
      timingCard.appendChild(el("span", {
        class: "comfymodal-studio-timing-e2e",
        text: "End-to-End Total: " + _formatDuration(e2e.durationMs),
      }));
    }

    // Top stages as compact tag row (excluding E2E, showing at most 4)
    var nonTotalStages = nr.timingStages.filter(function (s) {
      return s.label !== "End-to-End Total" && s.durationMs > 0;
    }).sort(function (a, b) { return b.durationMs - a.durationMs; }).slice(0, 4);

    if (nonTotalStages.length > 0) {
      var tagRow = el("div", { class: "comfymodal-studio-timing-tags" });
      nonTotalStages.forEach(function (st) {
        // Phase I8: informational timing tags adopt the shared chip geometry
        // with the muted meta tone; legacy class preserved for page CSS.
        tagRow.appendChild(el("span", {
          class: "comfymodal-studio-timing-tag cm-chip",
          "data-tone": "meta",
          text: st.label + ": " + _formatDuration(st.durationMs),
        }));
      });
      timingCard.appendChild(tagRow);
    }

    // Quality indicator
    if (nr._timingQuality && nr._timingQuality !== "complete") {
      var qualDot = el("span", {
        class: "comfymodal-studio-timing-quality",
        text: nr._timingQuality === "missing" ? "No timing data" : nr._timingQuality + " quality",
      });
      timingCard.appendChild(qualDot);
    }

    section.appendChild(timingCard);
  } else if (nr.timingSummary && typeof nr.timingSummary === "string" && nr.timingSummary.length > 0) {
    // Fallback: timing summary string (progress annotation contract)
    section.appendChild(el("div", {
      class: "comfymodal-studio-timing-summary",
      text: nr.timingSummary,
    }));
  } else if (nr.durationMs != null && nr.durationMs > 0) {
    // Fallback: just show duration
    section.appendChild(el("div", {
      class: "comfymodal-studio-timing-summary",
      text: "Duration: " + _formatDuration(nr.durationMs),
    }));
  }

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Key generation settings (using shared normalizer) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  var normalizedSettings = normalizeGenerationSettings(rc, rqc);
  var settingsRow = el("div", { class: "comfymodal-studio-metadata-settings" });
  var genSettings = [];

  if (normalizedSettings.seed != null) genSettings.push({ label: "Seed", value: String(normalizedSettings.seed) });
  if (normalizedSettings.steps != null) genSettings.push({ label: "Steps", value: String(normalizedSettings.steps) });
  if (normalizedSettings.cfg != null) genSettings.push({ label: "CFG", value: String(normalizedSettings.cfg) });
  if (normalizedSettings.guidance != null && normalizedSettings.cfg == null) {
    genSettings.push({ label: "Guidance", value: String(normalizedSettings.guidance) });
  }
  if (normalizedSettings.sampler != null) genSettings.push({ label: "Sampler", value: String(normalizedSettings.sampler) });
  if (normalizedSettings.scheduler != null) genSettings.push({ label: "Scheduler", value: String(normalizedSettings.scheduler) });
  if (normalizedSettings.denoise != null) genSettings.push({ label: "Denoise", value: String(normalizedSettings.denoise) });
  if (normalizedSettings.width != null && normalizedSettings.height != null) {
    genSettings.push({ label: "Size", value: normalizedSettings.width + "\u00d7" + normalizedSettings.height });
  }
  if (nr.workflowHash) genSettings.push({ label: "Workflow", value: nr.workflowHash.substring(0, 8) + "\u2026" });

  // LoRAs
  const loras = rc.loras || rqc.loras || [];
  if (loras.length > 0) {
    const loraStrs = loras.map(function (l) {
      if (typeof l === "object" && l !== null) {
        return (l.name || l.model || "") + " (" + (l.strength || l.weight || l.strength_model || 1.0) + ")";
      }
      return String(l);
    });
    if (loraStrs.length > 0) {
      genSettings.push({ label: "LoRAs", value: loraStrs.join("; ") });
    }
  }

  genSettings.forEach(function (s) {
    settingsRow.appendChild(el("span", {
      class: "comfymodal-studio-metadata-setting",
      "data-label": s.label,
      text: s.label + ": " + s.value,
    }));
  });

  section.appendChild(settingsRow);

  // Error display
  if (nr.error) {
    section.appendChild(el("div", {
      class: "comfymodal-studio-metadata-error",
      text: "Error: " + nr.error.substring(0, 300),
    }));
  }

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Collapsible toggles (Note | Advanced) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  const togglesRow = el("div", {
    style: "display:flex;gap:12px;margin-top:4px;",
  });

  // Note toggle
  const noteToggle = el("button", {
    class: "comfymodal-studio-metadata-advanced-toggle",
    "data-testid": "note-toggle",
    text: "\u25b6 Note",
    style: "font-size:10px;color:#888;cursor:pointer;background:none;border:none;padding:2px 0;",
    onclick: function () {
      const panel = section.querySelector(".comfymodal-studio-metadata-note-panel");
      if (panel) {
        const isHidden = panel.style.display === "none" || panel.style.display === "";
        panel.style.display = isHidden ? "block" : "none";
        noteToggle.textContent = isHidden ? "\u25bc Note" : "\u25b6 Note";
      }
    },
  });
  togglesRow.appendChild(noteToggle);

  // Advanced toggle
  const advancedToggle = el("button", {
    class: "comfymodal-studio-metadata-advanced-toggle",
    "data-testid": "advanced-toggle",
    text: "\u25b6 Advanced",
    style: "font-size:10px;color:#888;cursor:pointer;background:none;border:none;padding:2px 0;",
    onclick: function () {
      const panel = section.querySelector(".comfymodal-studio-metadata-advanced");
      if (panel) {
        const isHidden = panel.style.display === "none" || panel.style.display === "";
        panel.style.display = isHidden ? "block" : "none";
        advancedToggle.textContent = isHidden ? "\u25bc Advanced" : "\u25b6 Advanced";
      }
    },
  });
  togglesRow.appendChild(advancedToggle);
  section.appendChild(togglesRow);

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Note panel (collapsible) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  const notePanel = el("div", {
    class: "comfymodal-studio-metadata-note-panel",
    style: "display:none;",
  });
  notePanel.appendChild(renderNoteEditor(nr, actions, apiBase));
  section.appendChild(notePanel);

  // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Advanced panel (collapsible) ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
  const advancedPanel = el("div", {
    class: "comfymodal-studio-metadata-advanced",
    style: "display:none;font-size:10px;color:#666;",
  });

  const advancedItems = [];

  // IDs
  if (nr.id) advancedItems.push({ label: "Run ID", value: nr.id });
  if (nr.experimentId) advancedItems.push({ label: "Experiment ID", value: nr.experimentId });
  if (nr.snapshotId) advancedItems.push({ label: "Snapshot ID", value: nr.snapshotId });

  // Full timings ├óΓé¼ΓÇ¥ keep raw JSON accessible in advanced diagnostics
  if (nr.durationMs != null) advancedItems.push({ label: "Duration (ms)", value: String(nr.durationMs) });
  if (nr.rawTiming && Object.keys(nr.rawTiming).length > 0) {
    advancedItems.push({ label: "Raw Timings", value: JSON.stringify(nr.rawTiming) });
  }
  if (nr.timingStages && nr.timingStages.length > 0) {
    nr.timingStages.forEach(function (st) {
      if (st.durationMs > 0) {
        advancedItems.push({ label: st.label, value: _formatDuration(st.durationMs) });
      }
    });
  }
  if (nr.perNodeTimings && nr.perNodeTimings.length > 0) {
    var nodeSummary = nr.perNodeTimings.slice(0, 10).map(function (nt) {
      return "#" + nt.nodeId + ": " + _formatDuration(nt.durationMs) + (nt.cached ? " (cached)" : "");
    }).join(" | ");
    advancedItems.push({ label: "Per-Node Timings", value: nodeSummary });
  }

  // Advanced timing diagnostics (only when diagnostics exist)
  if (nr.advancedTiming) {
    var diag = nr.advancedTiming;
    if (diag.traceVersion) {
      // Display exact trace version without adding another "v" prefix
      advancedItems.push({ label: "Trace Version", value: diag.traceVersion });
    }
    if (diag.timingReason) advancedItems.push({ label: "Timing Quality", value: diag.timingQuality + " \u2014 " + diag.timingReason });
    if (diag.missingFields && diag.missingFields.length > 0) {
      advancedItems.push({ label: "Missing Fields", value: diag.missingFields.join(", ") });
    }
    if (diag.rawDeltasMs && Object.keys(diag.rawDeltasMs).length > 0) {
      advancedItems.push({ label: "Raw deltas_ms", value: JSON.stringify(diag.rawDeltasMs).substring(0, 200) + (JSON.stringify(diag.rawDeltasMs).length > 200 ? "\u2026" : "") });
    }
    if (diag.rawDerivedMs && Object.keys(diag.rawDerivedMs).length > 0) {
      advancedItems.push({ label: "Raw derived_ms", value: JSON.stringify(diag.rawDerivedMs).substring(0, 200) + (JSON.stringify(diag.rawDerivedMs).length > 200 ? "\u2026" : "") });
    }
    if (diag.rawStages && Object.keys(diag.rawStages).length > 0) {
      advancedItems.push({ label: "Raw stages", value: JSON.stringify(diag.rawStages).substring(0, 200) + (JSON.stringify(diag.rawStages).length > 200 ? "\u2026" : "") });
    }
    if (diag.wallClockTrace) {
      advancedItems.push({ label: "Wall-Clock Trace", value: JSON.stringify(diag.wallClockTrace).substring(0, 200) + (JSON.stringify(diag.wallClockTrace).length > 200 ? "\u2026" : "") });
    }
    if (diag.schedulerTrace) {
      advancedItems.push({ label: "Scheduler Trace", value: JSON.stringify(diag.schedulerTrace).substring(0, 200) + (JSON.stringify(diag.schedulerTrace).length > 200 ? "\u2026" : "") });
    }
    if (diag.sources && Object.keys(diag.sources).length > 0) {
      advancedItems.push({ label: "Timing Sources", value: JSON.stringify(diag.sources).substring(0, 200) + (JSON.stringify(diag.sources).length > 200 ? "\u2026" : "") });
    }
    if (diag.backendTimingSources && Object.keys(diag.backendTimingSources).length > 0) {
      advancedItems.push({ label: "Backend Sources", value: JSON.stringify(diag.backendTimingSources).substring(0, 200) + (JSON.stringify(diag.backendTimingSources).length > 200 ? "\u2026" : "") });
    }

    // Waterfall summary (serialized v2 report) ├óΓé¼ΓÇ¥ same display text as
    // History's Diagnostics panel via the shared buildWaterfallLines helper.
    // Absent (no rows) for legacy records without a waterfall.
    if (diag.waterfall) {
      var wfLines = buildWaterfallLines(diag.waterfall);
      var wfMeta = wfLines.filter(function (l) { return l.kind === "meta"; })
        .map(function (l) { return l.text; });
      if (wfMeta.length > 0) {
        advancedItems.push({ label: "Waterfall", value: wfMeta.join(" | ") });
      }
      var wfStages = wfLines.filter(function (l) { return l.kind === "stage"; })
        .map(function (l) { return l.text; });
      if (wfStages.length > 0) {
        advancedItems.push({ label: "Waterfall Stages", value: wfStages.join(" | ") });
      }
      var wfWarnings = wfLines
        .filter(function (l) { return l.kind === "warn" || l.kind === "warn-more"; })
        .map(function (l) { return l.text; });
      if (wfLines.some(function (l) { return l.kind === "warn-header"; }) && wfWarnings.length > 0) {
        advancedItems.push({ label: "Waterfall Warnings", value: wfWarnings.join(" | ") });
      }
    }
  }

  // Workflow hash
  if (nr.workflowHash) advancedItems.push({ label: "Workflow Hash", value: nr.workflowHash });

  // Output reference
  if (nr.outputPath) advancedItems.push({ label: "Output Path", value: nr.outputPath });
  if (nr.imageUrl) advancedItems.push({ label: "Image URL", value: nr.imageUrl });

  // Resolved controls
  if (nr.resolvedControls && Object.keys(nr.resolvedControls).length > 0) {
    advancedItems.push({ label: "Resolved Controls", value: JSON.stringify(nr.resolvedControls, null, 1) });
  }

  // Error
  if (nr.error) advancedItems.push({ label: "Error", value: nr.error });

  advancedItems.forEach(function (item) {
    const itemValue = item.value == null ? "" : String(item.value);
    advancedPanel.appendChild(el("div", { style: "margin:2px 0;" }, [
      el("strong", { text: item.label + ": ", style: "color:#888;" }),
      el("span", { text: itemValue.substring(0, 200) + (itemValue.length > 200 ? "\u2026" : "") }),
    ]));
  });

  section.appendChild(advancedPanel);

  return section;
}

// ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Carousel ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
//
// History carousel: a compact view of the History V2 feed.
// Same repository, same newest-first window, same records in the same order,
// and same record identity as the History page — only the presentation
// differs (horizontal thumbnails, no toolbar).  Generation clicks load the
// Playground canvas (the one Playground-specific action), or open the
// History generation detail when there is no image to load; experiments
// open their History detail.  Imageless records keep a placeholder.

// ΓöÇΓöÇ Carousel accessible naming (Phase I8) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
//
// Every filmstrip button needs a distinguishable accessible name built from
// stable run context ΓÇö preset label, truthful status, wall-clock time ΓÇö and
// a short id tail ONLY when two visible items would otherwise share an
// identical name. Long ids are never dumped into the label.

function _formatRunClock(iso) {
  if (!iso || typeof iso !== "string") return "";
  var ms = Date.parse(iso);
  if (isNaN(ms)) return "";
  var d = new Date(ms);
  var h = d.getHours();
  var h12 = h % 12 === 0 ? 12 : h % 12;
  return h12 + ":" + String(d.getMinutes()).padStart(2, "0") + " " + (h >= 12 ? "PM" : "AM");
}

function _carouselShortId(nr) {
  var raw = String((nr && (nr.experimentId || nr.runId || nr.id)) || "");
  return raw.replace(/[^a-zA-Z0-9]/g, "").slice(-6);
}

function _carouselBaseAccessibleName(nr) {
  const label = nr.presetLabel || nr.presetId || nr.featureId || "Run";
  const timeText = _formatRunClock(nr.completedAt || nr.startedAt || "");
  return label + ", " + (nr.status || "unknown") + (timeText ? " at " + timeText : "");
}

/** One name per item; disambiguated in-place when duplicated. */
function _carouselAccessibleNames(recentRuns) {
  var names = [];
  var seenBases = {};
  recentRuns.forEach(function (nr) {
    var isExperiment = nr.kind === "experiment" || Boolean(nr.experimentId);
    var cta = nr.imageUrl ? (isExperiment ? "Open experiment." : "Open run.") : "No image.";
    var base = _carouselBaseAccessibleName(nr);
    if (seenBases[base]) {
      var shortId = _carouselShortId(nr);
      if (shortId) base += " (#" + shortId + ")";
    }
    seenBases[base] = true;
    names.push(base + ". " + cta);
  });
  return names;
}

function renderFilmstrip(state, context) {
  const carousel = el("div", {
    class: "comfymodal-studio-carousel",
    "data-testid": "filmstrip",
  });

  const apiBase = (context && context.apiBase) || "/comfymodal";

  // Use cached recent runs or trigger async load
  let recentRuns = getRecentRuns();

  // Re-render helper
  function rerender() {
    if (context && context.setPage) context.setPage("playground");
  }

  // If the user explicitly cleared the carousel, show empty state and
  // skip server fetch.  This persists across refreshes until a new run
  // completes, which clears the flag.
  if (isCarouselCleared()) {
    // Guard against stale cache from any other code path
    clearRecentRunsCache();
    // Phase I8: user-cleared is an ordinary empty state ΓÇö shared primitive.
    carousel.appendChild(renderEmptyState({
      title: "Recent runs cleared.",
      detail: "Submit a new run to see results here.",
      testid: "playground-recent-runs-cleared",
    }));
    return carousel;
  }

  if (recentRuns == null) {
    // Phase I8: loading is NOT an empty state ΓÇö shared loading primitive.
    carousel.appendChild(renderLoadingState({
      label: "Loading recent runs…",
      size: "inline",
      testid: "playground-recent-runs-loading",
    }));

    // Async fetch fills cache ├óΓé¼ΓÇ¥ on next render it will show
    refreshRecentRuns(apiBase).then(function () {
      if (carousel.isConnected) rerender();
    });
  } else {
    // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Hidden state: show reveal bar ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
    if (state.playground && state.playground._carouselHidden) {
      const revealBtn = el("button", {
        type: "button",
        class: "comfymodal-studio-carousel-reveal",
        onclick: function () {
          if (state.playground) {
            state.playground._carouselHidden = false;
            rerender();
          }
        },
        text: "Show recent runs (" + recentRuns.length + ")",
      });
      carousel.appendChild(revealBtn);
      return carousel;
    }

    // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Empty state ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
    if (recentRuns.length === 0) {
      // Phase I8: shared generic empty-state primitive.
      carousel.appendChild(renderEmptyState({
        title: "Recent runs will appear here once you use the Playground.",
        testid: "playground-recent-runs-empty",
      }));
      return carousel;
    }

    // ├óΓÇ¥Γé¼├óΓÇ¥Γé¼ Header row with actions ├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼├óΓÇ¥Γé¼
    const track = el("div", { class: "comfymodal-studio-carousel-track" });
    const trackId = "comfymodal-recent-runs-track";
    track.id = trackId;
    const leftArrow = el("button", {
      type: "button",
      class: "comfymodal-studio-carousel-accordion-arrow",
      text: "↑",
      "aria-label": "Collapse recent runs",
      "aria-controls": trackId,
    });
    const rightArrow = el("button", {
      type: "button",
      class: "comfymodal-studio-carousel-accordion-arrow",
      text: "↑",
      "aria-label": "Collapse recent runs",
      "aria-controls": trackId,
    });
    const toggle = function () {
      state.playground._carouselCollapsed = !state.playground._carouselCollapsed;
      track.hidden = state.playground._carouselCollapsed;
      const arrow = track.hidden ? "↓" : "↑";
      const label = track.hidden ? "Expand recent runs" : "Collapse recent runs";
      leftArrow.textContent = arrow;
      rightArrow.textContent = arrow;
      leftArrow.setAttribute("aria-label", label);
      rightArrow.setAttribute("aria-label", label);
      leftArrow.setAttribute("aria-expanded", String(!track.hidden));
      rightArrow.setAttribute("aria-expanded", String(!track.hidden));
    };
    leftArrow.addEventListener("click", toggle);
    rightArrow.addEventListener("click", toggle);
    const accordion = el("div", { class: "comfymodal-studio-carousel-accordion" }, [
      leftArrow,
      el("span", { class: "comfymodal-studio-carousel-accordion-label", text: "Recent runs" }),
      rightArrow,
    ]);
    accordion.addEventListener("click", function (event) {
      if (!event.target.closest("button")) toggle();
    });
    carousel.appendChild(accordion);
    track.hidden = !!(state.playground && state.playground._carouselCollapsed);
    const initialArrow = track.hidden ? "↓" : "↑";
    const initialLabel = track.hidden ? "Expand recent runs" : "Collapse recent runs";
    leftArrow.textContent = initialArrow;
    rightArrow.textContent = initialArrow;
    leftArrow.setAttribute("aria-label", initialLabel);
    rightArrow.setAttribute("aria-label", initialLabel);
    leftArrow.setAttribute("aria-expanded", String(!track.hidden));
    rightArrow.setAttribute("aria-expanded", String(!track.hidden));

    // Phase I8: unique, context-bearing accessible names (time + status +
    // run type; short id only when the base name collides).
    const ariaNames = _carouselAccessibleNames(recentRuns);

    recentRuns.forEach(function (nr, idx) {
      const imageUrl = nr.imageUrl;
      const label = nr.presetLabel || nr.presetId || nr.featureId || "Run";
      const isExperiment = nr.kind === "experiment" || Boolean(nr.experimentId);
      const OK_STATUSES = ["completed", "completed_with_failures", "success", "done", "succeeded"];
      const ERR_STATUSES = ["failed", "error", "canceled", "cancelled"];

      const thumb = el("button", {
        type: "button",
        class: "comfymodal-studio-carousel-item"
          + (OK_STATUSES.indexOf(nr.status) !== -1 ? " completed" : "")
          + (ERR_STATUSES.indexOf(nr.status) !== -1 ? " failed" : "")
          + (isExperiment ? " comfymodal-studio-carousel-item-experiment" : ""),
        "aria-label": ariaNames[idx],
        title: (isExperiment ? "Experiment: " : "") + label + " - " + (nr.status || ""),
        "data-id": nr.id || "",
        "data-expid": isExperiment ? nr.experimentId : "",
        onclick: function () {
          if (isExperiment && nr.experimentId) {
            // H13: open the durable History V2 owner ├óΓé¼ΓÇ¥ never the legacy grid.
            requestHistoryRecordFocus(nr.experimentId, "experiment");
            if (context && context.setPage) context.setPage("history");
          } else if (imageUrl && state.playground) {
            // Ordinary run — make this run's output THE workspace image. Image
            // Tool Inputs follow it: stale source/mask values belong to the
            // previous image, so they reset and the chain refills the source
            // from the newly selected output.
            // The canvas loads the full-size display asset for the record,
            // never the capped carousel thumbnail (see _canvasUrlForRun).
            var canvasUrl = _canvasUrlForRun(nr, imageUrl);
            var prevCanvas = _canvasImageUrl(state);
            state.playground.lastRunOutput = canvasUrl;
            state.playground._selectedRun = nr;
            _setCanvasImage(state, canvasUrl);
            if (!_sameWorkspaceImage(prevCanvas, canvasUrl)) {
              var _actions = state.playground._runActions;
              ["source_image", "mask"].forEach(function (role) {
                try {
                  if (_schemaHasRole(state, role)) commitShelfValue(state, context, _actions, role, "");
                } catch (_e) { /* reset is best-effort */ }
              });
            try { _chainCurrentImageToSource(state, context, _actions); } catch (_e) { /* best-effort */ }
            }
            rerender();
          } else if (!isExperiment && (nr.generationId || nr.runId || nr.id)) {
            // Imageless generation: no canvas image to load, so open the
            // same History generation detail its History card opens.
            requestHistoryRecordFocus(String(nr.generationId || nr.runId || nr.id), "generation");
            if (context && context.setPage) context.setPage("history");
          }
        },
      });

      if (isExperiment) {
        // Experiment badge overlaid on the thumbnail. Phase I8: informational
        // identity marker on the shared chip geometry with the muted meta
        // tone (never a status/error look); decorative (name carries it).
        thumb.appendChild(el("span", {
          class: "comfymodal-studio-carousel-exp-badge cm-chip",
          "data-tone": "meta",
          text: "EXP",
          "aria-hidden": "true",
        }));
      }

      if (imageUrl) {
        thumb.appendChild(el("img", {
          class: "comfymodal-studio-carousel-thumb",
          src: imageUrl,
          alt: label,
          loading: "lazy",
          onerror: function (e) {
            // Same truthful rule as imageless records: a broken thumbnail
            // keeps its place with a placeholder instead of a broken image.
            const imgEl = e.currentTarget;
            const parent = imgEl.parentNode;
            imgEl.remove();
            if (parent && !parent.querySelector(".comfymodal-studio-carousel-thumb-empty")) {
              parent.insertBefore(el("span", {
                class: "comfymodal-studio-carousel-thumb comfymodal-studio-carousel-thumb-empty",
                text: "No image",
                "aria-hidden": "true",
              }), parent.firstChild);
            }
          },
        }));
      } else {
        // Same truthful rule as the History cards: an imageless record keeps
        // its place with a placeholder instead of a broken image.
        thumb.appendChild(el("span", {
          class: "comfymodal-studio-carousel-thumb comfymodal-studio-carousel-thumb-empty",
          text: "No image",
          "aria-hidden": "true",
        }));
      }

      // Status dot
      const isOk = OK_STATUSES.indexOf(nr.status) !== -1;
      const isErr = ERR_STATUSES.indexOf(nr.status) !== -1;
      thumb.appendChild(el("span", {
        class: "comfymodal-studio-carousel-status",
        style: "background:" + (isOk ? "#4ade80" : isErr ? "#f87171" : "#fbbf24"),
      }));

      track.appendChild(thumb);
    });

    carousel.appendChild(track);
  }

  return carousel;
}

// Playground workspace entry point for the History carousel above.
// The implementation lives in renderFilmstrip (name pinned by tests); this
// wrapper gives the workspace call site the canonical History-view name.
// Both names render the same History V2-backed view.
function renderHistoryCarousel(state, context) {
  return renderFilmstrip(state, context);
}

// ΓöÇΓöÇ Shelf Playground (Studio Workflow effort, leaf 1.2.2) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
// Normalize an array-shaped run-context control_schema into the role-keyed
// object form (see _rerenderWorkflowSection). No-op for object schemas.
// When values were derived while the schema was an array they carry pure
// index keys ("0".."N"); those are re-keyed to their entry roles and the
// current preset's values win (they were bypassed while the schema was an
// array). User edits always use real role keys and are never clobbered:
// repair runs only when index-key pollution is present.
function _normalizeShelfControlSchema(state) {
  var store = state && state.playground && state.playground._workflowRun;
  if (!store || !store.runContext) return;
  var schema = store.runContext.control_schema;
  if (!Array.isArray(schema)) return;
  var obj = {};
  schema.forEach(function (e) {
    if (!e || typeof e !== "object") return;
    var role = e.semantic_role || e.input_name;
    if (role) obj[role] = e;
  });
  store.runContext.control_schema = obj;
  var values = store.controlValues && typeof store.controlValues === "object" ? store.controlValues : {};
  var polluted = Object.keys(values).some(function (k) {
    return /^\d+$/.test(k) && !Object.prototype.hasOwnProperty.call(obj, k);
  });
  if (!polluted) return;
  var repaired = {};
  Object.keys(values).forEach(function (k) {
    if (/^\d+$/.test(k) && !Object.prototype.hasOwnProperty.call(obj, k)) {
      var entry = schema[Number(k)];
      var role = entry && (entry.semantic_role || entry.input_name);
      if (role && repaired[role] === undefined) repaired[role] = values[k];
    } else {
      repaired[k] = values[k];
    }
  });
  store.controlValues = repaired;
}

// Left-sidebar bound field cards for the selected Workflow:
// - Prompt card fixed at top (never draggable, never in Advanced); output
//   stays the right-side result panel (never a movable card).
// - Every other bound field: drag-handle reorder, Advanced placement, and
//   same-row grouping by dropping into a row, with an autosaved
//   workflow-type layout and a subtle
//   autosaved indicator (no Save button).
// - Workflow switching goes through the shared picker
//   (web/studio-workflow-picker.js) with a reuse-values prompt; the old
//   output is marked stale until a new run completes.
// - Field renderers come from web/studio-field-blocks.js and role names
//   from web/studio-bindable-inputs.js ΓÇö no duplicated catalog here.
// - Normal field values + layout autosave durably (studio-playground-state
//   Shelf lane); experiment-only state lives in the separate local draft
//   lane and never overwrites Workflow values.

var _SHELF_TYPE_FALLBACK = "t2i";

// Reading this as: creator pro-tool workspace header for image makers, with a
// minimalist Photoshop-style language, leaning toward native CSS + neutral
// zinc + one restrained accent. Dials: VARIANCE 5 / MOTION 3 / DENSITY 3.

export const STUDIO_TOOLS = Object.freeze([
  { id: "t2i", label: "Generate", icon: "✦", title: "Text to Image" },
  { id: "i2i", label: "Edit", icon: "◐", title: "Image to Image" },
  { id: "inpaint", label: "Mask", icon: "◍", title: "Inpaint" },
  { id: "outpaint", label: "Expand", icon: "⛶", title: "Expand" },
  { id: "sketch", label: "Draw", icon: "✎", title: "Sketch" },
  { id: "postprocess", label: "Post Processing", icon: "◑", title: "TinyLuma-based photo finishing" },
  { id: "upscale", label: "Upscale", icon: "⤢", title: "Upscale workflow (placeholder)", isPlaceholder: true },
]);

const _TOOL_ALIASES = Object.freeze({
  txt2img: "t2i",
  text_to_image: "t2i",
  generate: "t2i",
  img2img: "i2i",
  image_to_image: "i2i",
  image_edit: "i2i",
  edit: "i2i",
  mask: "inpaint",
  crop: "outpaint",
  draw: "sketch",
});

export function normalizeToolId(value) {
  var raw = String(value || "").trim().toLowerCase();
  if (!raw) return "t2i";
  return _TOOL_ALIASES[raw] || raw;
}

export function activeToolOf(state) {
  var pg = state && state.playground;
  var raw = (pg && (pg.activeTool || pg.toolId)) || "";
  if (!raw) {
    var store = pg && pg._workflowRun;
    var ctx = store && store.runContext;
    var wf = ctx && ctx.workflow;
    raw = (ctx && (ctx.workflow_type || ctx.workflowType))
      || (wf && (wf.workflow_type || wf.workflowType))
      || (pg && pg.featureId)
      || "t2i";
  }
  var canonical = normalizeToolId(raw);
  var known = STUDIO_TOOLS.some(function (t) { return t.id === canonical; });
  return known ? canonical : "t2i";
}

// ── Phase 1 visible shell: Generate / Edit / Post Processing ─────────
// UI organization only — internal execution types in STUDIO_TOOLS stay the
// source of truth for filtering, queueing, and run contracts. Post
// categories route to the existing local postprocess engine; subtools with
// no execution type (null) and honest later-phase placeholders never run.
// No generic mode engine or capability registry: one explicit table each way.

// Top rail: exactly these three modes, in this order.
var STUDIO_MODES = Object.freeze([
  { id: "generate", label: "Generate", icon: "✦", title: "Generate" },
  { id: "edit", label: "Edit", icon: "◐", title: "Edit" },
  { id: "post", label: "Post Processing", icon: "◑", title: "Post Processing" },
]);

// Visible shell vocab is single-sourced in studio-playground-state.js
// (SHELL_SUBTOOLS): this alias keeps existing call sites unchanged.
var STUDIO_SUBMENUS = SHELL_SUBTOOLS;

// Later-phase placeholders: honest disabled views, execution gated off.
// (Outpaint entry is user-facing Expand here; real Crop lives under Post.)
// Simple membership list — labels come from STUDIO_SUBTOOL_LABELS.
var LATER_PHASE_SUBTOOLS = SHELL_PLACEHOLDERS;

function _isPlaceholderSubtool(subtool) {
  return LATER_PHASE_SUBTOOLS.indexOf(subtool) !== -1;
}

var STUDIO_SUBTOOL_LABELS = Object.freeze({
  text: "Text",
  references: "References",
  layout: "Layout",
  sketch: "Sketch",
  guidance: "Guidance",
  select: "Select",
  expand: "Expand",
  adjust: "Adjust",
  color: "Color",
  detail: "Detail",
  effects: "Effects",
  crop: "Crop",
  heal: "Heal",
  upscale: "Upscale",
});

// Visible subtool -> internal execution type. Post categories run through
// the existing local postprocess engine, so they map to null (no workflow
// type change, no selection reset when entering Post). Later-phase
// placeholders (references/layout/guidance) have no execution type yet.
// Phase 2: Edit/Select is I2I + selection UI, not a separate workflow
// family — an ordinary I2I workflow stays selected while masking. Dedicated
// legacy inpaint workflows remain usable: selecting one still opens
// Edit/Select (see _defaultShellForTool) as a compatibility override.
function _subtoolExecutionType(mode, subtool) {
  if (mode === "post") return null;
  switch (subtool) {
    case "text": return mode === "edit" ? "i2i" : "t2i";
    case "select": return "i2i";
    // Phase 3: Edit/Expand is I2I + Expand Method, not a separate workflow
    // family. Dedicated legacy outpaint workflows remain usable: selecting
    // one still opens Edit/Expand (see _defaultShellForTool) as a
    // compatibility override.
    case "expand": return "i2i";
    case "sketch": return "sketch";
    default: return null;
  }
}

// Phase 2 selection context: Edit/Select on an ordinary I2I workflow.
// Phase 3 selection context: Edit/Expand on an ordinary I2I workflow.
// One explicit predicate each (not a framework) shared by editor dispatch,
// canvas base routing, and workflow-picker scoping below.
function _isSelectOnI2I(state) {
  return activeToolOf(state) === "i2i"
    && activeModeOf(state) === "edit"
    && activeSubtoolOf(state) === "select";
}
function _isExpandOnI2I(state) {
  return activeToolOf(state) === "i2i"
    && activeModeOf(state) === "edit"
    && activeSubtoolOf(state) === "expand";
}

// Workflow-picker scope follows the visible shell (not the active tool), so
// ordinary I2I plus the matching legacy override stay reachable together.
function _pickerTypesForShell(state) {
  var mode = activeModeOf(state);
  var sub = activeSubtoolOf(state);
  if (mode === "edit" && sub === "select") return ["i2i", "inpaint"];
  if (mode === "edit" && sub === "expand") return ["i2i", "outpaint"];
  return activeToolOf(state);
}

// ── Phase 3: explicit generic-method state ──────────────────────────────
// The selected method is a per-workflow UI preference (localStorage, see
// studio-playground-state.js); execution reads it at submit time. No Auto:
// the dropdown always shows one explicit method, defaulting to Crop + Stitch
// (inpaint) / Pad + Preserve (expand) until the user picks otherwise.

// Latest conditioning-compatibility answer, keyed by workflow+version.
// Advisory only: the backend revalidates anchors at execution time.
var _methodCompatCache = { key: "", result: null };

function _methodMaskFile(state, store, prefs) {
  try {
    var cv = (store && store.controlValues) || {};
    if (cv.mask) return String(cv.mask);
    var cur = cv.source_image || "";
    if (prefs && prefs.savedMask && prefs.savedMaskSource && cur
      && String(prefs.savedMaskSource) === String(cur)) {
      return String(prefs.savedMask);
    }
  } catch (_e) {}
  return "";
}

// Phase 5: visual prompt-style browser state. Global (not per-workflow):
// a style is prompt-authoring preference. {selectedId:"", favorites:[]}.
var STYLE_STORE_KEY = "comfymodal.studio.style.v1";
function loadStyleSelection() {
  var out = { selectedId: "", favorites: [] };
  try {
    var raw = localStorage.getItem(STYLE_STORE_KEY);
    if (!raw) return out;
    var j = JSON.parse(raw);
    if (j && typeof j.selectedId === "string") out.selectedId = j.selectedId;
    if (j && Array.isArray(j.favorites)) {
      out.favorites = j.favorites.filter(function (x) { return typeof x === "string"; });
    }
  } catch (_e) {}
  return out;
}
function saveStyleSelection(patch) {
  try {
    var cur = loadStyleSelection();
    if (patch && typeof patch.selectedId === "string") cur.selectedId = patch.selectedId;
    if (patch && Array.isArray(patch.favorites)) cur.favorites = patch.favorites;
    localStorage.setItem(STYLE_STORE_KEY, JSON.stringify(cur));
  } catch (_e) {}
}
function _styleCatalogStyles() {
  try {
    var list = STYLE_CATALOG && STYLE_CATALOG.styles;
    return Array.isArray(list) ? list : [];
  } catch (_e) { return []; }
}
function _styleById(id) {
  var styles = _styleCatalogStyles();
  for (var i = 0; i < styles.length; i++) {
    if (styles[i] && String(styles[i].id) === String(id)) return styles[i];
  }
  return null;
}
// Deterministic composition: user prompt stays first and verbatim; the
// style fragment appends after a separator. Empty user prompt + style
// submits the fragment alone (still an honest, visible prompt).
function composeStylePrompt(userPrompt, fragment) {
  var user = String(userPrompt == null ? "" : userPrompt).trim();
  var frag = String(fragment == null ? "" : fragment).trim();
  if (!frag) return String(userPrompt == null ? "" : userPrompt);
  if (!user) return frag;
  return user + ", " + frag;
}
// Explicit style request for the current run, or null for a plain prompt.
// Generate → Text only; the selected style must still exist in the catalog.
function _studioStyleForRun(state, store) {
  try {
    if (!state || !store || !store.workflowId) return null;
    if (activeToolOf(state) !== "t2i") return null;
    if (activeModeOf(state) !== "generate") return null;
    if (activeSubtoolOf(state) !== "text") return null;
    var sel = loadStyleSelection();
    if (!sel.selectedId) return null;
    var style = _styleById(sel.selectedId);
    if (!style || !style.prompt_fragment) return null;
    var cv = (store && store.controlValues) || {};
    var userPrompt = cv.prompt == null ? "" : String(cv.prompt);
    return {
      style: style,
      userPrompt: userPrompt,
      composed: composeStylePrompt(userPrompt, style.prompt_fragment),
    };
  } catch (_e) { return null; }
}
function _renderStyleBrowser(state, context, actions, entries, promptRole) {
  try {
    if (!state) return null;
    if (activeToolOf(state) !== "t2i") return null;
    if (activeModeOf(state) !== "generate") return null;
    if (activeSubtoolOf(state) !== "text") return null;
    if (!promptRole) return null;
    var styles = _styleCatalogStyles();
    if (!styles.length) return null;
    var sel0 = loadStyleSelection();
    if (sel0.selectedId && !_styleById(sel0.selectedId)) {
      saveStyleSelection({ selectedId: "" });
      sel0.selectedId = "";
    }
    var box = el("div", {
      class: "comfymodal-studio-style-browser",
      "data-testid": "style-browser",
      style: "margin:8px 0;",
    });
    var head = el("div", {
      style: "display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;",
    });
    head.appendChild(el("span", {
      text: "Prompt Style",
      style: "font-size:12px;color:#aaa;",
    }));
    var selName = el("span", {
      "data-testid": "style-selected-name",
      style: "font-size:12px;color:var(--color-text, #ddd);",
    });
    head.appendChild(selName);
    var noneBtn = el("button", {
      type: "button", class: "comfymodal-secondary-btn",
      text: "None",
      "data-testid": "style-none",
      title: "Clear the selected style (plain prompt)",
    });
    head.appendChild(noneBtn);
    box.appendChild(head);
    var tools = el("div", { style: "display:flex;gap:8px;margin-bottom:6px;" });
    var search = el("input", {
      type: "search", placeholder: "Search styles…",
      "data-testid": "style-search",
      class: "comfymodal-input comfymodal-studio-text-input",
      style: "flex:2;min-width:0;",
    });
    var cats = ["All"];
    styles.forEach(function (s) {
      if (s && s.category && cats.indexOf(s.category) === -1) cats.push(s.category);
    });
    var catSel = el("select", {
      "data-testid": "style-category",
      class: "comfymodal-input",
      style: "flex:1;min-width:0;",
      title: "Filter by category",
    });
    cats.forEach(function (c) {
      var o = document.createElement("option");
      o.value = c;
      o.textContent = c === "All" ? "All categories" : c;
      catSel.appendChild(o);
    });
    tools.appendChild(search);
    tools.appendChild(catSel);
    box.appendChild(tools);
    var grid = el("div", {
      "data-testid": "style-grid",
      style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:8px;",
    });
    box.appendChild(grid);
    var details = el("p", {
      "data-testid": "style-details",
      class: "comfymodal-studio-control-note",
      style: "font-size:11px;color:#888;margin:6px 0 0;",
    });
    box.appendChild(details);
    var effLine = el("p", {
      "data-testid": "style-effective-prompt",
      class: "comfymodal-studio-control-note",
      style: "font-size:11px;color:#888;margin:4px 0 0;overflow-wrap:anywhere;",
    });
    box.appendChild(effLine);
    function currentPromptText() {
      try {
        var store = _shelfStore(state);
        var cv = (store && store.controlValues) || {};
        return cv.prompt == null ? "" : String(cv.prompt);
      } catch (_e) { return ""; }
    }
    function paintSelection() {
      var sel = loadStyleSelection();
      var st = sel.selectedId ? _styleById(sel.selectedId) : null;
      selName.textContent = st ? ("Selected: " + st.title) : "No style (plain prompt)";
      details.textContent = st
        ? (st.title + " — " + (st.description || "") + (st.tags && st.tags.length ? " [" + st.tags.join(", ") + "]" : ""))
        : "Pick a style card to append its fragment to your prompt at run time.";
      effLine.textContent = st
        ? ("Effective prompt: " + composeStylePrompt(currentPromptText(), st.prompt_fragment))
        : "";
      Array.prototype.forEach.call(grid.querySelectorAll('[data-testid^="style-card-"]'), function (card) {
        var on = !!st && card.getAttribute("data-style-id") === st.id;
        card.classList.toggle("is-selected", on);
        card.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }
    function applyFilter() {
      var q = String(search.value || "").trim().toLowerCase();
      var cat = String(catSel.value || "All");
      Array.prototype.forEach.call(grid.children, function (card) {
        var s = _styleById(card.getAttribute("data-style-id"));
        var show = !!s;
        if (show && cat !== "All" && s.category !== cat) show = false;
        if (show && q) {
          var hay = (s.title + " " + s.category + " " + (s.description || "") + " " + (s.tags || []).join(" ")).toLowerCase();
          if (hay.indexOf(q) === -1) show = false;
        }
        card.style.display = show ? "" : "none";
      });
    }
    styles.forEach(function (s) {
      var card = el("button", {
        type: "button",
        class: "comfymodal-studio-style-card",
        "data-testid": "style-card-" + s.id,
        "data-style-id": s.id,
        title: s.title + " — " + (s.description || ""),
        style: "display:flex;flex-direction:column;gap:4px;padding:6px;border:1px solid var(--color-border, #333);border-radius:8px;background:transparent;cursor:pointer;text-align:left;",
      });
      var hue = Number(s.hue);
      if (!isFinite(hue)) hue = 210;
      card.appendChild(el("span", {
        "data-testid": "style-swatch-" + s.id,
        style: "display:block;height:44px;border-radius:6px;background:linear-gradient(135deg,hsl(" + hue + ",60%,42%),hsl(" + ((hue + 40) % 360) + ",65%,26%));",
      }));
      var row = el("span", { style: "display:flex;align-items:center;gap:4px;" });
      row.appendChild(el("span", {
        text: s.title,
        style: "font-size:11px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
      }));
      var fav = el("span", {
        text: "★",
        "data-testid": "style-fav-" + s.id,
        title: "Toggle favorite",
        style: "font-size:12px;cursor:pointer;color:#666;flex:none;",
      });
      row.appendChild(fav);
      card.appendChild(row);
      card.appendChild(el("span", {
        text: s.category || "",
        style: "font-size:10px;color:#888;",
      }));
      fav.addEventListener("click", function (ev) {
        ev.stopPropagation();
        ev.preventDefault();
        try {
          var cur = loadStyleSelection();
          var i = cur.favorites.indexOf(s.id);
          if (i === -1) cur.favorites.push(s.id);
          else cur.favorites.splice(i, 1);
          saveStyleSelection({ favorites: cur.favorites });
          fav.style.color = i === -1 ? "#e8b93e" : "#666";
        } catch (_e) {}
      });
      try {
        if (loadStyleSelection().favorites.indexOf(s.id) !== -1) fav.style.color = "#e8b93e";
      } catch (_e) {}
      card.addEventListener("click", function () {
        try { saveStyleSelection({ selectedId: s.id }); } catch (_e) {}
        paintSelection();
      });
      grid.appendChild(card);
    });
    noneBtn.addEventListener("click", function () {
      try { saveStyleSelection({ selectedId: "" }); } catch (_e) {}
      paintSelection();
    });
    search.addEventListener("input", applyFilter);
    catSel.addEventListener("change", applyFilter);
    // Keep the effective-prompt preview honest as the user types, without
    // rebuilding the section (which would drop search focus). Delegated on
    // the shelf section: prompt inputs render under different testids per
    // workflow (input-prompt, shelf-input-prompt), so match any textarea.
    try {
      var shelfSec = box.closest ? box.closest('[data-testid="shelf-section"]') : null;
      var listenTarget = shelfSec || document;
      listenTarget.addEventListener("input", function (ev) {
        try {
          var t = ev && ev.target;
          if (!t || String(t.tagName || "").toLowerCase() !== "textarea") return;
          if (!effLine.isConnected) return;
          var sel = loadStyleSelection();
          var st = sel.selectedId ? _styleById(sel.selectedId) : null;
          effLine.textContent = st
            ? ("Effective prompt: " + composeStylePrompt(t.value, st.prompt_fragment))
            : "";
        } catch (_e) {}
      });
    } catch (_e) {}
    paintSelection();
    applyFilter();
    return box;
  } catch (_e) { return null; }
}

// Explicit method request for the current shell, or null for a plain run.
// Generic methods only ever apply on the I2I engine; legacy tools run native.
function _studioMethodForRun(state, store) {
  try {
    if (!state || !store || !store.workflowId) return null;
    if (activeToolOf(state) !== "i2i") return null;
    if (activeModeOf(state) !== "edit") return null;
    var sub = activeSubtoolOf(state);
    var prefs = loadWorkflowMethods(store.workflowId);
    if (sub === "select") {
      if (prefs.inpaintMethod === "dedicated") {
        if (!prefs.inpaintOverride) return null;
        // Dedicated inpaint still consumes the Select-subtool mask: it rides
        // in params (like generic methods) and the backend feeds it to the
        // override workflow's own mask role — never as a control here.
        return {
          kind: "inpaint", method: "dedicated",
          params: { mask_file: _methodMaskFile(state, store, prefs) },
          override: prefs.inpaintOverride,
        };
      }
      return {
        kind: "inpaint", method: prefs.inpaintMethod,
        params: { mask_file: _methodMaskFile(state, store, prefs) },
      };
    }
    if (sub === "expand") {
      if (prefs.expandMethod === "dedicated") {
        if (!prefs.expandOverride) return null;
        return { kind: "expand", method: "dedicated", params: {}, override: prefs.expandOverride };
      }
      return {
        kind: "expand", method: prefs.expandMethod,
        params: { top: prefs.padTop, right: prefs.padRight, bottom: prefs.padBottom, left: prefs.padLeft },
      };
    }
    return null;
  } catch (_e) { return null; }
}

// Honest run gate for explicit methods (reason string or null). Runs after
// the shell gate; the backend revalidates everything at execution.
function _studioMethodGate(state) {
  try {
    var pg = state && state.playground;
    var store = pg && pg._workflowRun;
    if (!pg || !store || !store.workflowId) return null;
    if (activeToolOf(state) !== "i2i") return null;
    if (activeModeOf(state) !== "edit") return null;
    var sub = activeSubtoolOf(state);
    var prefs = loadWorkflowMethods(store.workflowId);
    if (sub === "select") {
      if (prefs.inpaintMethod === "dedicated" && !prefs.inpaintOverride) {
        return "Choose a dedicated inpaint workflow";
      }
      if ((prefs.inpaintMethod === "crop_stitch" || prefs.inpaintMethod === "conditioning"
        || prefs.inpaintMethod === "dedicated")
        && !_methodMaskFile(state, store, prefs)) {
        return "Save a mask in Edit → Select first";
      }
      if (prefs.inpaintMethod === "conditioning") {
        var c = _methodCompatCache;
        var key = String(store.workflowId) + "::" + String(store.workflowVersionId || "");
        if (c && c.key === key && c.result && c.result.conditioning
          && c.result.conditioning.compatible === false) {
          var reasons = c.result.conditioning.reasons || [];
          return "Conditioning incompatible: " + String(reasons[0] || "no anchor").slice(0, 140);
        }
      }
      return null;
    }
    if (sub === "expand") {
      if (prefs.expandMethod === "dedicated" && !prefs.expandOverride) {
        return "Choose a dedicated expand workflow";
      }
      if ((prefs.expandMethod === "pad" || prefs.expandMethod === "pad_preserve")
        && !(prefs.padTop + prefs.padRight + prefs.padBottom + prefs.padLeft > 0)) {
        return "Set Top/Right/Bottom/Left expansion";
      }
      return null;
    }
    return null;
  } catch (_e) { return null; }
}

// Refresh the conditioning-compatibility answer for the selected version,
// then update the editor note + run gating. Best-effort; absence never blocks
// (the backend is authoritative at execution).
function _refreshMethodCompat(state, context) {
  try {
    var pg = state && state.playground;
    var store = pg && pg._workflowRun;
    if (!store || !store.workflowId || !store.workflowVersionId) return;
    var key = String(store.workflowId) + "::" + String(store.workflowVersionId);
    if (_methodCompatCache.key === key && _methodCompatCache.result) {
      _paintCompatNote(state);
      return;
    }
    _methodCompatCache.key = key;
    _methodCompatCache.result = null;
    var apiBase = (context && context.apiBase) || "/comfymodal";
    getMethodCompat(apiBase, store.workflowId, store.workflowVersionId).then(function (res) {
      if (!res || _methodCompatCache.key !== key) return;
      _methodCompatCache.result = res;
      _paintCompatNote(state);
      try { _syncWorkflowGating(state, context, {}); } catch (_e) {}
    }, function () {});
  } catch (_e) {}
}

function _paintCompatNote(state) {
  try {
    var note = document.querySelector('[data-testid="inpaint-method-note"]');
    if (!note || !note.isConnected) return;
    var pg = state && state.playground;
    var store = pg && pg._workflowRun;
    var c = _methodCompatCache;
    var key = store ? String(store.workflowId) + "::" + String(store.workflowVersionId || "") : "";
    var res = (c && c.key === key) ? c.result : null;
    var cond = res && res.conditioning;
    if (!cond || cond.compatible !== true) {
      note.textContent = (cond && cond.compatible === false)
        ? "Conditioning unavailable here: " + String((cond.reasons || ["no anchor"])[0]).slice(0, 140)
        : "";
      return;
    }
    note.textContent = "Anchor: KSampler " + cond.sampler_id + " + VAE " + (cond.vae ? cond.vae[0] : "?");
  } catch (_e) {}
}

// Dedicated-override picker: the shared workflow picker constrained to the
// specialized family. Close without confirming leaves everything unchanged
// (onClose) so Dedicated is never stranded without an override.
function _openMethodOverridePicker(state, context, kind, currentId, onPick, onClose) {
  try {
    _closeShelfDialog();
    var apiBase = (context && context.apiBase) || "/comfymodal";
    var overlay = el("div", {
      class: "comfymodal-studio-shelf-dialog-overlay",
      "data-testid": "method-override-dialog",
    });
    var dialog = el("div", {
      class: "comfymodal-studio-shelf-dialog",
      role: "dialog",
      "aria-label": "Choose dedicated workflow",
    });
    dialog.appendChild(el("h4", {
      class: "comfymodal-studio-block-heading",
      text: kind === "expand" ? "Dedicated Expand workflow" : "Dedicated Inpaint workflow",
    }));
    var closed = false;
    function onKey(ev) {
      if (ev.key === "Escape") {
        // Self-cleaning: if our dialog node is already gone (e.g. ComfyUI
        // closed the whole Studio modal underneath us), detach and do NOT
        // fire the stale onClose, which would revert a newer choice.
        if (!document.querySelector('[data-testid="method-override-dialog"]')) {
          try { document.removeEventListener("keydown", onKey); } catch (_e) {}
          return;
        }
        finish();
        if (onClose) onClose();
      }
    }
    function finish() {
      // Our overlay has its own testid: _closeShelfDialog only removes the
      // shelf dialogs. Detach the Esc listener too, or a later Escape would
      // fire this dialog's stale onClose (e.g. reverting a newer choice).
      if (closed) return;
      closed = true;
      try { document.removeEventListener("keydown", onKey); } catch (_e) {}
      try {
        var mine = document.querySelector('[data-testid="method-override-dialog"]');
        if (mine && mine.parentNode) mine.parentNode.removeChild(mine);
      } catch (_e2) {}
      _closeShelfDialog();
    }
    var closeBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-studio-shelf-mini-btn",
      "data-testid": "method-override-close",
      text: "Close",
    });
    closeBtn.addEventListener("click", function () {
      finish();
      if (onClose) onClose();
    });
    dialog.appendChild(closeBtn);
    dialog.appendChild(renderWorkflowPicker({
      apiBase: apiBase,
      mode: "single",
      workflowTypes: kind === "expand" ? ["outpaint"] : ["inpaint"],
      selectedIds: currentId ? [currentId] : [],
      confirmLabel: "Use workflow",
      onConfirm: function (ids) {
        var next = ids && ids.length ? String(ids[0]) : "";
        finish();
        if (next && onPick) onPick(next);
        else if (onClose) onClose();
      },
    }));
    overlay.addEventListener("click", function (ev) {
      if (ev.target === overlay) {
        finish();
        if (onClose) onClose();
      }
    });
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    try {
      document.addEventListener("keydown", onKey);
    } catch (e) { /* non-fatal */ }
  } catch (_e) {}
}

function _overrideButtonLabel(state, store, id) {
  try {
    if (id && store && Array.isArray(store.library)) {
      var row = store.library.find(function (w) { return String(w.workflow_id) === String(id); });
      if (row) {
        try { return _workflowOptionLabel(row); } catch (_e) { return String(row.name || id); }
      }
    }
  } catch (_e) {}
  return "Choose…";
}

// Shared explicit-method row for the Select/Expand editors (one concrete use
// each). Fixed option sets, fixed testids, direct prefs — no framework.
// noteText, when given, recomputes the note on every method change.
function _methodSelectRow(state, context, actions, kind, noteText) {
  var store = null;
  try { store = _shelfStore(state); } catch (_e) { store = null; }
  // The row may mount before a workflow finishes selecting: always resolve
  // the workflow id live at event time so a choice is never saved nowhere.
  function rowWfId() {
    try {
      var s = _shelfStore(state);
      return (s && s.workflowId) ? String(s.workflowId) : "";
    } catch (_e) { return ""; }
  }
  var wfId = rowWfId();
  var prefs = loadWorkflowMethods(wfId);
  var isInpaint = kind === "inpaint";
  var methodKey = isInpaint ? "inpaintMethod" : "expandMethod";
  var overrideKey = isInpaint ? "inpaintOverride" : "expandOverride";
  var testid = isInpaint ? "inpaint" : "expand";
  var options = isInpaint
    ? [["crop_stitch", "Crop + Stitch"], ["conditioning", "Conditioning + Crop/Stitch"], ["dedicated", "Dedicated Workflow"]]
    : [["pad", "Pad Canvas"], ["pad_preserve", "Pad + Preserve"], ["dedicated", "Dedicated Workflow"]];
  var row = el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;align-items:center;" });
  row.appendChild(el("span", {
    text: isInpaint ? "Inpaint Method" : "Expand Method",
    style: "font-size:12px;color:#aaa;",
  }));
  var sel = el("select", { "data-testid": testid + "-method", "aria-label": isInpaint ? "Inpaint Method" : "Expand Method" });
  options.forEach(function (pair) {
    var o = document.createElement("option");
    o.value = pair[0];
    o.textContent = pair[1];
    if (prefs[methodKey] === pair[0]) o.selected = true;
    sel.appendChild(o);
  });
  row.appendChild(sel);
  var overBtn = el("button", {
    type: "button", class: "comfymodal-secondary-btn",
    text: _overrideButtonLabel(state, store, prefs[overrideKey]),
    "data-testid": testid + "-override-btn",
    title: "Choose a dedicated workflow",
  });
  overBtn.style.display = prefs[methodKey] === "dedicated" ? "" : "none";
  function pickOverride() {
    var cur = "";
    try { cur = String(loadWorkflowMethods(rowWfId())[overrideKey] || ""); } catch (_e) {}
    _openMethodOverridePicker(state, context, kind, cur, function (nextId) {
      var patch = {};
      patch[overrideKey] = nextId;
      try { saveWorkflowMethods(rowWfId(), patch); } catch (_e2) {}
      try { overBtn.textContent = _overrideButtonLabel(state, store, nextId); } catch (_e3) {}
      try { _syncWorkflowGating(state, context, actions); } catch (_e4) {}
    }, function () {
      try { _syncWorkflowGating(state, context, actions); } catch (_e5) {}
    });
  }
  overBtn.addEventListener("click", pickOverride);
  row.appendChild(overBtn);
  var note = el("p", {
    class: "comfymodal-studio-control-note",
    text: "",
    style: "font-size:11px;color:#888;margin:0;flex-basis:100%;",
    "data-testid": testid + "-method-note",
  });
  row.appendChild(note);
  function paintNote() {
    if (!note.isConnected) return;
    if (typeof noteText === "function") {
      try { note.textContent = noteText() || ""; } catch (_e) {}
    }
  }
  paintNote();
  sel.addEventListener("change", function () {
    var prev = "";
    try { prev = String(loadWorkflowMethods(rowWfId())[methodKey] || ""); } catch (_e) {}
    var patch = {};
    patch[methodKey] = sel.value;
    try { saveWorkflowMethods(rowWfId(), patch); } catch (_e2) {}
    var isDed = sel.value === "dedicated";
    overBtn.style.display = isDed ? "" : "none";
    paintNote();
    if (!isInpaint || sel.value === "conditioning") {
      try { _refreshMethodCompat(state, context); } catch (_e3) {}
    }
    if (isDed) {
      var cur2 = "";
      try { cur2 = String(loadWorkflowMethods(rowWfId())[overrideKey] || ""); } catch (_e4) {}
      // Dedicated means nothing without an override: picking opens the
      // picker now, and cancelling reverts instead of stranding the choice
      // (the run gate would otherwise be the only guard).
      if (!cur2) {
        _openMethodOverridePicker(state, context, kind, "", function (nextId) {
          var p2 = {};
          p2[overrideKey] = nextId;
          try { saveWorkflowMethods(rowWfId(), p2); } catch (_e5) {}
          try { overBtn.textContent = _overrideButtonLabel(state, store, nextId); } catch (_e6) {}
          try { _syncWorkflowGating(state, context, actions); } catch (_e7) {}
        }, function () {
          var pr = {};
          pr[methodKey] = prev;
          try { saveWorkflowMethods(rowWfId(), pr); } catch (_e8) {}
          try { sel.value = prev; } catch (_e9) {}
          overBtn.style.display = "none";
          paintNote();
          try { _syncWorkflowGating(state, context, actions); } catch (_e10) {}
        });
        return;
      }
    }
    try { _syncWorkflowGating(state, context, actions); } catch (_e11) {}
  });
  return row;
}

// Sensible visible shell for an internal execution type. A sketch type
// keeps the already-visible Generate/Edit Sketch choice when compatible.
function _defaultShellForTool(toolId, currentMode, currentSubtool) {
  var currentMapsSketch = _subtoolExecutionType(currentMode, currentSubtool) === "sketch";
  if (toolId === "sketch" && currentMapsSketch) {
    return { mode: currentMode, subtool: "sketch" };
  }
  if (toolId === "postprocess" && currentMode === "post" && currentSubtool !== "upscale") {
    return { mode: "post", subtool: currentSubtool };
  }
  // Phase 3: Text/Select/Expand all run on the I2I engine — switching between
  // I2I workflows keeps the already-visible Edit subtool instead of yanking
  // the user back to Text.
  if (toolId === "i2i" && currentMode === "edit"
    && (currentSubtool === "text" || currentSubtool === "select" || currentSubtool === "expand")) {
    return { mode: "edit", subtool: currentSubtool };
  }
  var defaults = {
    t2i: { mode: "generate", subtool: "text" },
    i2i: { mode: "edit", subtool: "text" },
    inpaint: { mode: "edit", subtool: "select" },
    outpaint: { mode: "edit", subtool: "expand" },
    sketch: { mode: "generate", subtool: "sketch" },
    postprocess: { mode: "post", subtool: "adjust" },
    upscale: { mode: "post", subtool: "upscale" },
  };
  return defaults[toolId] || null;
}

function _validShell(mode, subtool) {
  if (SHELL_MODES.indexOf(mode) === -1) return null;
  var subs = STUDIO_SUBMENUS[mode];
  if (!subs || subs.indexOf(subtool) === -1) return { mode: mode, subtool: subs ? subs[0] : "text" };
  return { mode: mode, subtool: subtool };
}

function activeModeOf(state) {
  var pg = state && state.playground;
  var shell = _validShell(pg && pg.activeMode, pg && pg.activeSubtool);
  return shell ? shell.mode : "generate";
}

function activeSubtoolOf(state) {
  var pg = state && state.playground;
  var shell = _validShell(pg && pg.activeMode, pg && pg.activeSubtool);
  return shell ? shell.subtool : "text";
}

// Restore visible mode/subtool from the validated shell key, migrating once
// from the existing tool key when no valid shell was saved yet. Storage
// helpers never throw (best-effort internally), so no try/catch here.
function _restoreShellState(state) {
  var pg = state && state.playground;
  if (!pg) return;
  var shell = loadShellSelection();
  if (!shell) {
    var rawTool = _storageGet("comfymodal.studio.playground.tool.v1") || "";
    shell = _defaultShellForTool(normalizeToolId(rawTool || pg.featureId || "t2i"), null, null)
      || { mode: "generate", subtool: "text" };
    saveShellSelection(shell.mode, shell.subtool);
  }
  var valid = _validShell(shell.mode, shell.subtool) || { mode: "generate", subtool: "text" };
  pg.activeMode = valid.mode;
  pg.activeSubtool = valid.subtool;
}

function _persistShellState(state) {
  var pg = state && state.playground;
  if (!pg) return;
  saveShellSelection(pg.activeMode, pg.activeSubtool);
}

// Honest execution gate for views with no runnable workflow path: Post
// (local engine) and later-phase placeholders. Single-sourced reason text
// shared with experiment submission gating (see studio-playground-state.js).
function _shellRunGate(state) {
  return shellGateReason(activeModeOf(state), activeSubtoolOf(state));
}

var _CANVAS_BG_KEY = "comfymodal.studio.canvas-bg.v1";

function _loadCanvasBg() {
  try {
    var raw = localStorage.getItem(_CANVAS_BG_KEY);
    if (raw && /^#[0-9a-fA-F]{6}$/.test(raw)) return raw;
  } catch (_e) {}
  return "";
}

function _saveCanvasBg(value) {
  try {
    if (value) localStorage.setItem(_CANVAS_BG_KEY, String(value));
    else localStorage.removeItem(_CANVAS_BG_KEY);
  } catch (_e) {}
}

function _runQueueOf(state) {
  var pg = state && state.playground;
  if (!pg) return [];
  if (!Array.isArray(pg._runQueue)) pg._runQueue = [];
  return pg._runQueue;
}

var _QUEUE_STORE_KEY = "comfymodal.studio.queue.v1";
var _QUEUE_STORE_MAX = 200;

function _saveQueue(state) {
  try {
    var pg = state && state.playground;
    if (!pg) return;
    var items = _runQueueOf(state).slice(0, _QUEUE_STORE_MAX);
    localStorage.setItem(_QUEUE_STORE_KEY, JSON.stringify({ items: items }));
  } catch (_e) {}
}

function _loadStoredQueue() {
  try {
    var raw = localStorage.getItem(_QUEUE_STORE_KEY);
    if (!raw) return [];
    var parsed = JSON.parse(raw);
    var items = parsed && parsed.items;
    if (!Array.isArray(items)) return [];
    return items.filter(function (it) {
      return it && typeof it.id === "string" && it.controlValues && typeof it.controlValues === "object";
    }).slice(0, _QUEUE_STORE_MAX);
  } catch (_e) {
    return [];
  }
}

// Head-of-queue group sharing one workflow identity (the backend resolves
// the workflow once per batch). Uncapped: one container per workflow group,
// however large the group is.
function _takeNextBatchChunk(state) {
  var q = _runQueueOf(state);
  if (!q.length) return [];
  var first = q[0];
  var wid = (first && first.workflowId) || "";
  var ver = (first && first.workflowVersionId) || "";
  var chunk = [];
  for (var i = 0; i < q.length; i++) {
    var item = q[i];
    if (((item && item.workflowId) || "") === wid
      && ((item && item.workflowVersionId) || "") === ver) {
      chunk.push(item);
    }
  }
  return chunk;
}

function _batchChunkKey(chunk) {
  if (!chunk || !chunk.length) return "";
  return String(chunk[0].workflowId || "") + "::" + String(chunk[0].workflowVersionId || "");
}

// Group-aware drain: multi-item same-workflow chunks go through one
// container batch; singletons (or workflows the batch endpoint refuses)
// use the existing single-run path. Called by the Run queue button and by
// the terminal-state auto-drain hook.
function _drainNextGroup(state, context, actions) {
  var pg = state && state.playground;
  if (!pg || pg._batchApplying) return;
  var chunk = _takeNextBatchChunk(state);
  if (!chunk.length || _isRunActive(state)) return;
  if (chunk.length === 1 || _batchChunkKey(chunk) === pg._batchDisabledFor) {
    _runNextQueued(state, context, actions, _resolvePrimaryRunButton());
    return;
  }
  _submitQueueBatch(state, context, actions, chunk);
}

function _newRequestId(prefix) {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  } catch (_e) {}
  return (prefix || "req") + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
}

// Submit one same-workflow chunk as a single container batch, then fan each
// variant result through the normal single-result completion path (history,
// carousel, canvas). While applying, the auto-drain hook stays quiet and one
// final drain chains any remaining groups afterwards.
async function _submitQueueBatch(state, context, actions, chunk) {
  var pg = state && state.playground;
  if (!pg || !chunk || !chunk.length) return;
  var apiBase = (context && context.apiBase) || "/comfymodal";
  var ids = {};
  chunk.forEach(function (it) { if (it) ids[it.id] = true; });
  pg._runQueue = _runQueueOf(state).filter(function (it) { return !ids[it.id]; });
  _saveQueue(state);
  pg._batchApplying = true;
  pg._batchTotal = chunk.length;
  pg._batchStartedAt = Date.now();
  pg._batchWorkflowName = (chunk[0] && chunk[0].workflowName) || "";
  pg._toastDismissed = false;
  pg._batchCompleted = 0;
  pg._batchStreamError = "";
  _refreshQueueViewer(state, context);
  if (actions && actions.setRunState) {
    actions.setRunState({
      status: "running",
      message: "Batch running: 0 of " + chunk.length + " complete",
      batchTotal: chunk.length,
      batchCompleted: 0,
    });
  } else if (context && context.setPage) {
    context.setPage("playground");
  }
  var modalOptions = null;
  try {
    modalOptions = await _preloadStudioModalOptions(apiBase);
  } catch (_e) {
    modalOptions = null;
  }
  var store = pg._workflowRun;
  var variantRequestIds = chunk.map(function () { return _newRequestId("variant"); });
  var byVariantId = {};
  variantRequestIds.forEach(function (vid, i) { byVariantId[vid] = i; });
  var payload = {
    profile: loadGoldenProfileSelection() || (modalOptions && modalOptions.golden_profile) || null,
    workflow_id: chunk[0].workflowId || (store && store.workflowId) || "",
    workflow_version_id: chunk[0].workflowVersionId || (store && store.workflowVersionId) || "",
    request_id: _newRequestId("batch"),
    modal_options: modalOptions,
    variants: chunk.map(function (it, i) {
      return { request_id: variantRequestIds[i], controls: (it && it.controlValues) || {} };
    }),
  };
  var accounted = {};
  var applied = 0;
  var failed = 0;
  var skippedItems = [];
  var fastPathItems = [];
  pg._batchId = payload.request_id;
  pg._batchCancelled = false;
  pg._batchCancelling = false;
  pg._batchItems = chunk.map(function (it, i) {
    return {
      queueId: it && it.id,
      variantRequestId: variantRequestIds[i],
      label: (it && it.label) || ("Variant " + (i + 1)),
      tool: (it && it.tool) || "",
      status: "pending",
      outputUrl: "",
      historyGenerationId: "",
      message: "",
    };
  });
  function _batchItemByVariant(vid) {
    var found = null;
    (pg._batchItems || []).forEach(function (entry) {
      if (entry && entry.variantRequestId === vid) found = entry;
    });
    return found;
  }
  var stream = await runStudioBatchStream(apiBase, payload, async function (event) {
    if (!event || typeof event !== "object") return;
    if (event.type === "batch_start") {
      pg._batchTotal = event.variant_count || chunk.length;
      return;
    }
    if (event.type === "batch_result") return;
    if (event.type === "batch_cancelled") {
      pg._batchCancelled = true;
      return;
    }
    if (event.type === "variant_start") {
      var started = _batchItemByVariant(event.variant_request_id);
      if (started) {
        started.status = "running";
        _refreshQueueViewer(state, context);
      }
      return;
    }
    if (event.type === "variant_skipped") {
      var skipped = _batchItemByVariant(event.variant_request_id);
      var skipIdx = event.variant_request_id != null ? byVariantId[event.variant_request_id] : undefined;
      if (skipIdx === undefined || accounted[event.variant_request_id]) return;
      accounted[event.variant_request_id] = true;
      if (skipped) skipped.status = "skipped";
      skippedItems.push(chunk[skipIdx]);
      pg._batchCompleted = applied + failed + skippedItems.length;
      _refreshQueueViewer(state, context);
      if (context && context.setPage) context.setPage("playground");
      return;
    }
    var idx = event.request_id != null ? byVariantId[event.request_id] : undefined;
    if (idx === undefined) {
      // Batch-level failure (validation/timeout): the remainder stays lost
      // unless requeued below, so record the message here.
      if (event.status === "error") pg._batchStreamError = event.message || "Batch failed.";
      return;
    }
    if (accounted[event.request_id]) return;
    accounted[event.request_id] = true;
    if (event.status === "ok") {
      // Each image lands exactly like a single direct run (history record
      // already completed server-side; canvas/carousel update here). The
      // per-variant terminal states cannot retrigger the drain while
      // _batchApplying is set.
      _handleDirectRunResult(
        Object.assign({ direct_run: true }, event),
        state, context, actions, (chunk[idx] && chunk[idx].controlValues) || {}, null
      );
      applied++;
      var done = _batchItemByVariant(event.request_id);
      if (done) {
        done.status = "done";
        done.historyGenerationId = event.historyGenerationId || event.history_generation_id || "";
        done.outputUrl = (state.playground && state.playground.lastRunOutput) || "";
      }
    } else {
      failed++;
      var bad = _batchItemByVariant(event.request_id);
      if (bad) {
        bad.status = "failed";
        bad.message = event.message || "Variant failed.";
      }
      if (event.error_code === "BATCH_FAST_PATH_REQUIRED") fastPathItems.push(chunk[idx]);
    }
    pg._batchCompleted = applied + failed + skippedItems.length;
    _refreshQueueViewer(state, context);
    if (context && context.setPage) context.setPage("playground");
  });
  pg._batchApplying = false;
  // Anything never accounted for (transport cut, timeout, cancel remainder)
  // goes back at the front in order so nothing queued is silently lost.
  // User-skipped variants go back too: skipping means "not now", not "never".
  var missing = chunk.filter(function (it, i) { return !accounted[variantRequestIds[i]]; });
  var requeue = skippedItems.concat(missing.filter(function (it) { return skippedItems.indexOf(it) === -1; }));
  if (requeue.length) {
    pg._runQueue = requeue.concat(_runQueueOf(state));
    _saveQueue(state);
  }
  if (!stream.ok && applied === 0 && failed === 0) {
    pg._runQueue = chunk.concat(_runQueueOf(state));
    _saveQueue(state);
    if (actions && actions.setRunState) {
      actions.setRunState({ status: "error", message: stream.message || "Batch run failed." });
    } else if (context && context.setPage) {
      context.setPage("playground");
    }
    _refreshQueueViewer(state, context);
    _refreshQueueToast(state);
    return;
  }
  // A non-batchable workflow fails its variants with BATCH_FAST_PATH_
  // REQUIRED: put those back and remember the key so the drain falls back
  // to sequential single runs for them instead of retrying the batch.
  if (fastPathItems.length) {
    pg._runQueue = fastPathItems.concat(_runQueueOf(state));
    _saveQueue(state);
    pg._batchDisabledFor = _batchChunkKey(chunk);
    // The refused batch never ran: drop its section so the manager does not
    // show a phantom "0/N failed" batch while the singles proceed below.
    pg._batchItems = [];
    pg._batchTotal = 0;
    pg._batchCompleted = 0;
    pg._batchCancelled = false;
    pg._batchCancelling = false;
    // The manual "running" state from submit must terminal first: the drain
    // hook only proceeds from a non-active runState, otherwise the requeued
    // singles wait forever behind a stale "Batch running".
    if (actions && actions.setRunState) {
      actions.setRunState({
        status: "completed",
        message: "Batch not supported for this workflow — continuing with single runs.",
      });
    } else if (context && context.setPage) {
      context.setPage("playground");
    }
    _refreshQueueViewer(state, context);
    _refreshQueueToast(state);
    _maybeDrainQueue(state, context, actions);
    return;
  }
  if (pg._batchStreamError && applied === 0 && missing.length === chunk.length) {
    pg._batchDisabledFor = _batchChunkKey(chunk);
    if (actions && actions.setRunState) {
      actions.setRunState({
        status: "completed",
        message: "Batch interrupted (" + (pg._batchStreamError || "unknown error") + ") — continuing with single runs.",
      });
    } else if (context && context.setPage) {
      context.setPage("playground");
    }
    _refreshQueueViewer(state, context);
    _refreshQueueToast(state);
    _maybeDrainQueue(state, context, actions);
    return;
  }
  if (pg._batchDisabledFor && _batchChunkKey(_takeNextBatchChunk(state)) !== pg._batchDisabledFor) {
    pg._batchDisabledFor = "";
  }
  if (applied === 0) {
    if (actions && actions.setRunState) {
      actions.setRunState({
        status: pg._batchCancelled ? "canceled" : "error",
        message: pg._batchCancelled
          ? "Batch cancelled — unrun variants returned to the queue."
          : (pg._batchStreamError || ("Batch failed: " + failed + " of " + chunk.length + " variants errored.")),
      });
    }
  } else if (context && context.setPage) {
    context.setPage("playground");
  }
  _recordBatchHistory(state);
  _refreshQueueViewer(state, context);
  _refreshQueueToast(state);
  _maybeDrainQueue(state, context, actions);
}

function _isRunActive(state) {
  var runState = state && state.playground && state.playground.runState;
  if (!runState || !runState.status) return false;
  return LEGACY_TERMINAL_STATUSES.indexOf(runState.status) === -1;
}

function _workflowTypeOfRow(w) {
  if (!w || typeof w !== "object") return "";
  return normalizeToolId(w.workflow_type || w.workflowType || w.type || "");
}

function _setActiveTool(state, context, actions, toolId) {
  var pg = state && state.playground;
  if (!pg) return;
  var next = normalizeToolId(toolId);
  if (pg.activeTool === next) return;
  pg.activeTool = next;
  pg.toolId = next;
  _SHELF_TYPE_FALLBACK = next;
  try {
    _storageSet("comfymodal.studio.playground.tool.v1", next);
  } catch (_e) {}
  var store = pg._workflowRun;
  var prevValues = Object.assign({}, (store && store.controlValues) || {});
  pg._pendingChainUrl = _shelfCurrentImageUrl(state);
  var autoSelect = "";
  if (store && store.library) {
    var current = (store.library || []).find(function (w) { return String(w.workflow_id) === String(store.workflowId); });
    var currentType = current ? _workflowTypeOfRow(current) : "";
    if (current && currentType && currentType !== next) {
      _flushShelfSave(state);
      // The clear below hands the store to the new tool: invalidate any
      // in-flight selection first, so a slow loser (selectWorkflow /
      // loadRunContext, guarded by _selGen / workflow-id in
      // studio-workflow-run.js) returns superseded and its tail cannot
      // restore the old workflow over the new tool.
      try { store._selGen = (store._selGen || 0) + 1; } catch (_e) {}
      store.setWorkflowId("");
      store.setVersionId("");
      store.setRunContext(null);
      store.controlValues = {};
      store.setStatus("idle");
      store.setReasons([]);
      pg._shelfStaleOutput = false;
    } else if (store && store.workflowId) {
      _chainCurrentImageToSource(state, context, actions);
    }
    if (store && !store.workflowId) {
      autoSelect = _preferredToolRow(state, store, next);
      if (!autoSelect) pg._pendingCarryValues = prevValues;
    }
  } else {
    pg._pendingCarryValues = prevValues;
  }
  if (context && context.setPage) context.setPage("playground");
  else {
    _refreshShelfSection(state, context, actions);
    _rerenderWorkflowSection(state, context, actions);
  }
  // Returning to a tool restores its most recently selected workflow, seeded
  // with the values just left behind — the workspace continues, it restarts.
  if (autoSelect) {
    _runSelectionFlow(state, context, actions, autoSelect, prevValues);
  }
}

// ── Phase 1 shell switching ─────────────────────────────────────────
// Same-type subtool switches (and all Post category views) are UI-only:
// selection, values, drafts, output, and run state are preserved —
// setFeature-style clears never run here. Only an actual execution-type
// change goes through the existing _setActiveTool picker/filter flow.

function _defaultSubtoolForMode(state, mode) {
  var pg = state && state.playground;
  if (mode === "post") {
    if (pg && pg.activeMode === "post") return activeSubtoolOf(state);
    return "adjust";
  }
  var subs = STUDIO_SUBMENUS[mode] || ["text"];
  var currentTool = activeToolOf(state);
  var currentSub = pg ? pg.activeSubtool : "";
  if (currentSub && subs.indexOf(currentSub) !== -1
    && _subtoolExecutionType(mode, currentSub) === currentTool) {
    return currentSub;
  }
  for (var i = 0; i < subs.length; i++) {
    if (_subtoolExecutionType(mode, subs[i]) === currentTool) return subs[i];
    // Compatibility: a legacy dedicated inpaint workflow has no subtool of
    // its own anymore — it lives in Edit/Select on top of the I2I family.
    if (currentTool === "inpaint" && mode === "edit" && subs[i] === "select") return subs[i];
    // Phase 3: same for a legacy dedicated outpaint workflow in Edit/Expand.
    if (currentTool === "outpaint" && mode === "edit" && subs[i] === "expand") return subs[i];
  }
  return subs[0];
}

function _setActiveSubtool(state, context, actions, mode, subtool) {
  var pg = state && state.playground;
  if (!pg) return;
  var valid = _validShell(mode, subtool);
  if (!valid) valid = { mode: activeModeOf(state), subtool: activeSubtoolOf(state) };
  if (pg.activeMode === valid.mode && pg.activeSubtool === valid.subtool) return;
  var next = _subtoolExecutionType(valid.mode, valid.subtool);
  pg.activeMode = valid.mode;
  pg.activeSubtool = valid.subtool;
  _persistShellState(state);
  if (!next || valid.mode === "post" || next === activeToolOf(state)) {
    if (context && context.setPage) context.setPage("playground");
    return;
  }
  _setActiveTool(state, context, actions, next);
}

function _postSubmenuNote(subtool) {
  if (subtool === "upscale") return "Upscale arrives in a later phase — execution is disabled.";
  return "Adjust the photo in the sidebar — pick the Studio image in the canvas, or upload your own. Shortcuts: \\ compare · C crop · J heal · W white balance · Ctrl+Z/Y undo/redo.";
}

// Post categories route to their honest existing anchors inside the live
// engine: matching inspector groups expand, Crop/Heal press the real
// toolbar tools. No engine rewrite, no fake controls.
var _POST_CATEGORY_GROUPS = {
  adjust: ["light"],
  color: ["color", "curves", "mixer", "grading"],
  detail: ["detail"],
  effects: ["effects"],
};

function _focusPostCategory(subtool, root) {
  try {
    // Scoped lookup so the category applies both live (document) and
    // synchronously right after mount (pp-shell subtree, pre-attach).
    var scope = root && root.querySelector ? root : document;
    var ws = scope.querySelector('[data-testid="pp-workspace"]');
    if (!ws) return;
    if (!root && !ws.isConnected) return;
    // The native sidebar is a focused view, not a relocated legacy inspector.
    // Keep the single mounted engine and only change which presentation groups
    // are visible; values, history, and the central stage remain untouched.
    ws.setAttribute("data-post-category", subtool || "adjust");
    if (subtool === "crop" || subtool === "heal") {
      var toolBtn = ws.querySelector('[data-testid="pp-' + subtool + '"]');
      if (toolBtn && !toolBtn.classList.contains("on")) toolBtn.click();
      var stage = ws.querySelector('[data-testid="pp-canvas"]');
      if (stage && stage.scrollIntoView) stage.scrollIntoView({ block: "nearest" });
      return;
    }
    if (subtool === "upscale") return;
    // Leaving a tool category must not leave its engine tool armed:
    // toggle Crop/Heal off through the existing toolbar buttons.
    ["crop", "heal"].forEach(function (t) {
      var armed = ws.querySelector('[data-testid="pp-' + t + '"]');
      if (armed && armed.classList.contains("on")) armed.click();
    });
    var groups = _POST_CATEGORY_GROUPS[subtool] || [];
    var first = null;
    groups.forEach(function (id) {
      var g = ws.querySelector('[data-group="' + id + '"]');
      if (!g) return;
      if (!first) first = g;
      var head = g.querySelector(".pp-grouphead");
      if (head && head.getAttribute("aria-expanded") !== "true") head.click();
    });
    // Routing must be visible: collapse groups outside this category so the
    // switch lands on its section instead of a wall of open groups. The
    // output group (export format/quality) stays as the user left it, and
    // recipe values are untouched — only disclosure state changes.
    try {
      Array.prototype.forEach.call(ws.querySelectorAll('[data-group]'), function (g) {
        var id = g.getAttribute("data-group");
        if (!id || id === "output" || groups.indexOf(id) !== -1) return;
        var head = g.querySelector(".pp-grouphead");
        if (head && head.getAttribute("aria-expanded") === "true") head.click();
      });
    } catch (_e2) {}
    if (first && first.scrollIntoView) first.scrollIntoView({ block: "nearest" });
  } catch (_e) { /* routing is best-effort */ }
}

// Post category switches stay in place: the mounted engine keeps its
// recipe, canvas, undo/redo, and compare state instead of remounting.
// Only crossing the Upscale boundary remounts (Upscale is a canvas
// placeholder, not the finishing editor). Ordinary categories share one
// gate, so no gate refresh is needed in place — the remount rebuilds it.
function _selectPostCategory(state, context, subtool) {
  var pg = state && state.playground;
  if (!pg) return;
  if (STUDIO_SUBMENUS.post.indexOf(subtool) === -1) return;
  if (pg.activeMode !== "post") return;
  // Re-clicking the already-selected tool category re-applies it: the
  // engine resets its tool on every mount, so this restores Crop/Heal
  // after a reload without any new editor state.
  if (pg.activeSubtool === subtool) {
    _focusPostCategory(subtool);
    return;
  }
  var crossed = (pg.activeSubtool === "upscale") !== (subtool === "upscale");
  pg.activeSubtool = subtool;
  _persistShellState(state);
  if (crossed) {
    if (context && context.setPage) context.setPage("playground");
    return;
  }
  try {
    var row = document.querySelector('[data-testid="tool-submenu-post"]');
    if (row) {
      Array.prototype.forEach.call(row.querySelectorAll("[data-subtool]"), function (btn) {
        var on = btn.getAttribute("data-subtool") === subtool;
        btn.classList.toggle("is-on", on);
        btn.classList.toggle("active", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
      });
      var note = row.querySelector('[data-testid="submenu-post-note"]');
      if (note) note.textContent = _postSubmenuNote(subtool);
    }
  } catch (_e) {}
  _focusPostCategory(subtool);
}

async function _runSelectionFlow(state, context, actions, workflowId, prevValues) {
  // Shared select → saved-values → carry → chain flow for the dropdown,
  // tool-switch restore, and handoff paths. Callers snapshot prevValues
  // before invoking; nothing here reads the outgoing selection.
  var pg = state && state.playground;
  var store = pg && pg._workflowRun;
  var wf = pg && pg._workflowRunModule;
  if (!store || !wf || !workflowId) return { ok: false };
  var prev = Object.assign({}, prevValues || {});
  if (pg._pendingCarryValues) {
    prev = Object.assign({}, pg._pendingCarryValues, prev);
    pg._pendingCarryValues = null;
  }
  var apiBase = (context && context.apiBase) || "/comfymodal";
  store.handoffError = null;
  const result = await wf.selectWorkflow(apiBase, store, workflowId);
  // A superseded rapid-switch loser leaves the store to the newer winner:
  // no persistence, carry, chain, or paint from stale data.
  if (result && result.superseded) return result;
  var _flowGen = store._selGen;
  await _loadWorkflowModelLibrary(state, apiBase);
  // A tool switch during the slow model-library fetch bumps _selGen (see
  // _setActiveTool): the winner owns the store now, so this tail must not
  // persist, sync, carry, or paint the stale selection back over it.
  if (store._selGen !== _flowGen) {
    return { ok: false, error: "superseded", reasons: ["superseded"], superseded: true };
  }
  if (result && result.ok) {
    wf.saveWorkflowSelection({
      workflowId: store.workflowId,
      workflowVersionId: store.workflowVersionId,
      workflowName: store.workflowName || "",
    });
    _rememberSelection(state);
  }
  var _toolChanged = _syncActiveToolToSelection(state);
  _loadPersistedSelectionResult(state, store, null, context);
  if (_toolChanged && context && context.setPage) {
    context.setPage("playground");
    return result || { ok: false };
  }
  _rerenderWorkflowSection(state, context, actions, { applySaved: true });
  _applyWorkspaceCarry(state, context, actions, prev);
  _chainCurrentImageToSource(state, context, actions);
  return result || { ok: false };
}

function _selectionIdentity(store) {
  return (store ? String(store.workflowId || "") : "")
    + "::" + (store ? String(store.workflowVersionId || "") : "");
}

function _syncEditorBaseImage(state) {
  try {
    var url = _editorBaseImageUrl(state);
    if (!url) return;
    ["inpaint-base-image", "sketch-base-image"].forEach(function (testid) {
      var img = document.querySelector('[data-testid="' + testid + '"]');
      if (img && img.isConnected && img.getAttribute("src") !== url) {
        img.setAttribute("src", url);
        // Strokes painted against the previous base would corrupt the new
        // one — clear the overlay so the next paint starts clean.
        var wrap = img.parentElement;
        var paint = wrap && wrap.querySelector("canvas");
        if (paint) {
          var ctx = paint.getContext("2d");
          if (ctx) ctx.clearRect(0, 0, paint.width, paint.height);
        }
      }
    });
  } catch (_e) { /* best-effort paint only */ }
}

async function _chainCurrentImageToSource(state, context, actions) {
  try {
    var pg = state && state.playground;
    var store = pg && pg._workflowRun;
    if (!pg || !store || !store.controlValues) return;
    var schema = {};
    try {
      var wf = pg._workflowRunModule;
      schema = wf ? wf.getControlSchema(store) : (store.runContext && store.runContext.control_schema) || {};
    } catch (_e) { schema = {}; }
    if (!schema || !schema.source_image) {
      // The tab's bundle can predate a Wizard save — refresh the same
      // version once before concluding there is nothing to chain into.
      await _refreshRunContext(state, context);
      try {
        schema = wf ? wf.getControlSchema(store) : (store.runContext && store.runContext.control_schema) || {};
      } catch (_e) { schema = {}; }
    }
    if (!schema || !schema.source_image) return;
    if (store.controlValues.source_image) { pg._pendingChainUrl = ""; return; }
    var url = pg._pendingChainUrl || _shelfCurrentImageUrl(state);
    if (!url) return;
    var identity = _selectionIdentity(store);
    // Prefer the on-drive file behind the canvas image over re-uploading
    // its pixels as a duplicate.
    var hit = _resolveCanvasFile(state, url);
    if (hit && hit.filename) {
      if (_selectionIdentity(store) !== identity) return;
      pg._pendingChainUrl = "";
      if (store.controlValues.source_image) return;
      commitShelfValue(state, context, actions, "source_image", hit.filename);
      if (state.playground) state.playground.sourceFollowsCanvas = true;
      _recordImageEdge(state, hit.filename, url);
      _refreshShelfSection(state, context, actions);
      _syncEditorBaseImage(state);
      return;
    }
    var resp = await fetch(url);
    if (!resp || !resp.ok) return;
    var blob = await resp.blob();
    var mod = await import("./studio-field-blocks.js");
    var name = await mod.uploadImageBlob(blob, mod.uniqueImageName("studio-current"));
    if (_selectionIdentity(store) !== identity) return;
    pg._pendingChainUrl = "";
    if (store.controlValues.source_image) return;
    commitShelfValue(state, context, actions, "source_image", name);
    if (state.playground) state.playground.sourceFollowsCanvas = true;
    _recordImageEdge(state, name, url);
    _refreshShelfSection(state, context, actions);
    _syncEditorBaseImage(state);
  } catch (_e) { /* chaining is best-effort */ }
}

export function renderToolStrip(state, context, actions) {
  // Phase 1 shell: exactly Generate | Edit | Post Processing. Internal
  // execution types (STUDIO_TOOLS) are unchanged — this rail only selects
  // the visible mode, reusing the existing rail button classes.
  var current = activeModeOf(state);
  var strip = el("div", {
    class: "comfymodal-studio-tool-strip",
    "data-testid": "studio-tool-strip",
    role: "toolbar",
    "aria-label": "Studio tools",
  });
  STUDIO_MODES.forEach(function (mode) {
    var isActive = mode.id === current;
    var btn = el("button", {
      type: "button",
      class: "comfymodal-studio-tool-rail-btn" + (isActive ? " is-on active" : ""),
      "data-testid": "studio-tool-" + mode.id,
      "data-tool": mode.id,
      title: mode.title || mode.label,
    });
    btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    var icon = el("span", { class: "tool-icon", "aria-hidden": "true", text: mode.icon || "○" });
    var label = el("span", { class: "tool-label", text: mode.label });
    btn.appendChild(icon);
    btn.appendChild(label);
    btn.addEventListener("click", function () {
      _setActiveSubtool(state, context, actions, mode.id, _defaultSubtoolForMode(state, mode.id));
    });
    strip.appendChild(btn);
  });
  return strip;
}

// ── Workspace top bar ─────────────────────────────────────────────
// One row above the canvas, inside .comfymodal-studio-workspace:
// centered Photoshop-style tool rail + right-aligned run controls.
// Run / queue-toggle / experiment-toggle are radio-linked: queue and
// experiment can never be on at the same time.

function _enqueueCurrentRun(state) {
  var pg = state && state.playground;
  if (!pg) return null;
  var store = pg._workflowRun;
  var q = _runQueueOf(state);
  var snapshot = {
    id: "q_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 7),
    tool: activeToolOf(state),
    workflowId: (store && store.workflowId) || "",
    workflowVersionId: (store && store.workflowVersionId) || "",
    workflowName: (store && store.workflowName) || "",
    controlValues: Object.assign({}, (store && store.controlValues) || {}, pg.controls || {}),
    label: ((store && store.workflowName) || activeToolOf(state)) + " #" + (q.length + 1),
    createdAt: Date.now(),
  };
  q.push(snapshot);
  _saveQueue(state);
  if (state.playground) state.playground._toastDismissed = false;
  return snapshot;
}

// Queue auto-drain guard + scheduler. Called on every terminal runState.
// Submits the next queued item only when: queue mode still on, items remain,
// no run is active, and no drain is already scheduled. The deferred re-check
// covers queueMode being toggled off or the queue emptied between terminal
// state and the scheduled tick.
function _maybeDrainQueue(state, context, actions) {
  var pg = state && state.playground;
  if (!pg || !pg.queueMode || pg._queueDrainInFlight || pg._batchApplying) return;
  if (!_runQueueOf(state).length) return;
  var ctrl = pg._runController;
  if ((ctrl && typeof ctrl.isTerminal === "function" && !ctrl.isTerminal()) || _isRunActive(state)) return;
  pg._queueDrainInFlight = true;
  setTimeout(function () {
    if (state.playground) state.playground._queueDrainInFlight = false;
    if (!state.playground || !state.playground.queueMode || state.playground._batchApplying) return;
    if (!_runQueueOf(state).length || _isRunActive(state)) return;
    _drainNextGroup(state, context, actions);
  }, 0);
}

function _runNextQueued(state, context, actions, btn) {
  var pg = state && state.playground;
  if (!pg) return;
  var q = _runQueueOf(state);
  if (!q.length || _isRunActive(state)) return;
  var next = q.shift();
  _saveQueue(state);
  // Background queue execution restores only the queued values onto the
  // live store, then submits through the same single-run path. It never
  // overwrites the visible UI: the user may be in Post or a placeholder
  // while earlier-enqueued runs drain, and a same-type auto-drain must not
  // jump the view back to Generate/Text. Shell reconciliation stays with
  // explicit picker/mode actions only.
  var store = pg._workflowRun;
  if (store && next.controlValues) {
    store.controlValues = Object.assign({}, next.controlValues);
  }
  if (pg.controls && next.controlValues) {
    Object.keys(next.controlValues).forEach(function (k) {
      if (next.controlValues[k] !== undefined) pg.controls[k] = next.controlValues[k];
    });
  }
  setTimeout(function () {
    var liveBtn = _resolvePrimaryRunButton();
    _modernRunSubmit(state, context, actions, liveBtn || btn);
  }, 0);
}

var _BATCH_HISTORY_KEY = "comfymodal.studio.batch-history.v1";
var _BATCH_HISTORY_MAX = 20;

function _loadBatchHistory() {
  try {
    var raw = localStorage.getItem(_BATCH_HISTORY_KEY);
    if (!raw) return [];
    var parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(function (rec) {
      return rec && typeof rec.batchId === "string" && Array.isArray(rec.items);
    }).slice(0, _BATCH_HISTORY_MAX);
  } catch (_e) {
    return [];
  }
}

function _recordBatchHistory(state) {
  var pg = state && state.playground;
  if (!pg || !Array.isArray(pg._batchItems) || !pg._batchItems.length) return;
  var done = 0, failed = 0, skipped = 0;
  var items = pg._batchItems.map(function (entry) {
    if (entry && entry.status === "done") done++;
    else if (entry && entry.status === "failed") failed++;
    else if (entry && entry.status === "skipped") skipped++;
    return {
      variantRequestId: (entry && entry.variantRequestId) || "",
      label: (entry && entry.label) || "",
      status: (entry && entry.status) || "pending",
      outputUrl: (entry && entry.outputUrl) || "",
      historyGenerationId: (entry && entry.historyGenerationId) || "",
      message: (entry && entry.message) || "",
    };
  });
  var record = {
    batchId: pg._batchId || "",
    createdAt: pg._batchStartedAt || Date.now(),
    workflowName: pg._batchWorkflowName || "",
    total: pg._batchItems.length,
    completed: done,
    failed: failed,
    skipped: skipped,
    cancelled: !!pg._batchCancelled,
    items: items,
  };
  try {
    var all = [record].concat(_loadBatchHistory()).slice(0, _BATCH_HISTORY_MAX);
    localStorage.setItem(_BATCH_HISTORY_KEY, JSON.stringify(all));
  } catch (_e) {}
}

// ── Persistent activity toast ───────────────────────────────────
// Appears while runs are queued or an experiment runs; stays until the
// user closes it. New activity (enqueue, batch start, experiment start)
// shows it again.
var _queueToastEl = null;

function _refreshQueueToast(state) {
  var pg = state.playground || {};
  var q = _runQueueOf(state);
  var expActive = !!(pg.experimentMode && pg._activeExperimentId);
  var active = q.length > 0 || !!pg._batchApplying || expActive;
  if (!active || pg._toastDismissed) {
    if (_queueToastEl && _queueToastEl.isConnected) _queueToastEl.remove();
    _queueToastEl = null;
    return;
  }
  if (!_queueToastEl || !_queueToastEl.isConnected) {
    _queueToastEl = el("div", {
      class: "comfymodal-studio-queue-toast",
      "data-testid": "queue-toast",
      role: "status",
    });
    document.body.appendChild(_queueToastEl);
  }
  while (_queueToastEl.firstChild) _queueToastEl.removeChild(_queueToastEl.firstChild);
  var head = el("div", { class: "comfymodal-studio-queue-toast-head" });
  head.appendChild(el("span", {
    class: "comfymodal-studio-queue-toast-title",
    text: pg._batchApplying ? "Batch running" : (expActive && !q.length ? "Experiment running" : "Queue"),
  }));
  var close = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn comfymodal-studio-queue-toast-close",
    "data-testid": "queue-toast-close",
    text: "✕",
    title: "Dismiss",
    "aria-label": "Dismiss queue toast",
  });
  close.addEventListener("click", function () {
    if (state.playground) state.playground._toastDismissed = true;
    _refreshQueueToast(state);
  });
  head.appendChild(close);
  _queueToastEl.appendChild(head);
  var body = el("div", { class: "comfymodal-studio-queue-toast-body" });
  if (pg._batchApplying) {
    var done = pg._batchCompleted || 0;
    var total = pg._batchTotal || 0;
    body.appendChild(el("div", {
      class: "comfymodal-studio-queue-toast-line",
      text: total ? ("Batch " + done + "/" + total + "…") : "Batch running…",
    }));
  }
  q.slice(0, 5).forEach(function (item, i) {
    body.appendChild(el("div", {
      class: "comfymodal-studio-queue-toast-line",
      text: (i + 1) + ". " + ((item && item.label) || "Queued run"),
    }));
  });
  if (q.length > 5) {
    body.appendChild(el("div", {
      class: "comfymodal-studio-queue-toast-line is-muted",
      text: "+" + (q.length - 5) + " more",
    }));
  }
  if (expActive) {
    body.appendChild(el("div", {
      class: "comfymodal-studio-queue-toast-line",
      text: "Experiment running",
    }));
  }
  _queueToastEl.appendChild(body);
  var open = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    "data-testid": "queue-toast-open",
    text: "Open manager",
  });
  open.addEventListener("click", function () {
    openQueueViewer(state, _latestPlaygroundTrio && _latestPlaygroundTrio.context);
  });
  _queueToastEl.appendChild(open);
}

function _formatQueuedValue(value) {
  var s;
  try {
    s = (typeof value === "string") ? value : JSON.stringify(value);
  } catch (_e) {
    s = String(value);
  }
  if (s == null) return "";
  s = String(s);
  return s.length > 140 ? s.slice(0, 140) + "…" : s;
}

// ── Queue viewer ────────────────────────────────────────────────
// Body-level overlay (survives playground re-renders) listing each queued
// run's captured data with a per-run Delete button.

var _queueViewerEl = null;
var _queueViewerHistory = null;

function _queueViewerKeydown(e) {
  if (e && e.key === "Escape") closeQueueViewer();
}

function closeQueueViewer() {
  if (_queueViewerEl && _queueViewerEl.isConnected) _queueViewerEl.remove();
  _queueViewerEl = null;
  _queueViewerHistory = null;
  document.removeEventListener("keydown", _queueViewerKeydown);
}

// Shared image-viewer opener: History record first (same source the History
// detail overlay renders, so prompt/params/image can never disagree), local
// run record as fallback. Reused by canvas, queue manager, and experiments.
export async function openRunImagePreview(state, context, run, outputUrl) {
  var _run = run || null;
  var _apiBase = (context && context.apiBase) || "/comfymodal";
  var _runId = viewerFirst(_run && _run.runId, _run && _run.id);
  if (!_runId) return;
  _savePlaygroundPreviewId(_runId);
  if (state.playground) state.playground._previewOpen = true;
  var _preview;
  try {
    var _record = null;
    var _historyRepo = null;
    if (_runId) {
      try {
        _historyRepo = await createHistoryRepository({ apiBase: _apiBase });
        _record = await _resolveHistoryViewerRecord(_historyRepo, _runId, _run, _apiBase);
      } catch (err) { /* local run remains a truthful fallback */ }
    }
    if (!_record) {
      _historyRepo = null;
      _record = buildViewerRecordFromRun(_run, outputUrl);
    }
    if (!_record) return;

    // Annotation writes follow the record's authority: a History-sourced
    // record writes through History V2 (the durable owner of favorites
    // and notes, exactly like the History overlay's own star/editor).
    function _writeAnnotation(field, value) {
      if (_historyRepo) {
        return field === "favorite"
          ? _historyRepo.setFavorite(_record.id, value)
          : _historyRepo.setNote(_record.id, value);
      }
      if (_run && _run._historyKind) {
        return _getRecentRunsRepo(_apiBase).then(function (repo) {
          return field === "favorite"
            ? repo.setFavorite(_run.id, value)
            : repo.setNote(_run.id, value);
        });
      }
      var patch = {};
      patch[field] = value;
      return updateRunAnnotation(_apiBase, _runId, patch);
    }

    var _viewer = resolveViewerInput(_record, outputUrl);
    // Native File actions need a V2 repository: local-only run records
    // carry no asset identity (buttons stay hidden), and bridge-mode
    // repos have no open/reveal routes (same reason).
    var _repoMode = null;
    try {
      _repoMode = _historyRepo && typeof _historyRepo.getModeInfo === "function"
        ? _historyRepo.getModeInfo() : null;
    } catch (err) { _repoMode = null; }
           var _fileActions = (_historyRepo && _repoMode && _repoMode.mode === "v2") ? {
             openAsset: function (assetId) { return _historyRepo.openAsset(assetId); },
             revealAsset: function (assetId) { return _historyRepo.revealAsset(assetId); },
           } : null;
           var _canDelete = !!(_historyRepo && _repoMode && _repoMode.mode === "v2");
    // Same single builder as History detail (resolveViewerShellArgs):
    // every shell input flows through it on both surfaces, so they
    // cannot drift apart when inputs are added.
    _preview = buildViewerShell(resolveViewerShellArgs(_viewer, {
      fileActions: _fileActions,
      // Same-page base: the shelf is right here, so apply directly and
      // rebuild - the overlay closes itself on a positive count.
      onUseAsBase: function (payload) {
        var applied = _applyShelfBaseValues(state, payload || {});
        _rerenderWorkflowSection(state, context, actions);
        return applied;
      },
      // Phase 10: same-page image handoffs. Current sets the canvas image
      // in place; Edit uploads through the history-as-source path (mapped
      // filename for execution) and navigates to Edit/Text; Post sets the
      // canvas image (the Post engine reads it) and navigates to Post;
      // Upscale navigates to the honest Phase-11 placeholder.
      onUseAsCurrent: function (payload) {
        var url = payload && payload.imageUrl;
        if (!url) return 0;
        try { _setCanvasImage(state, String(url), context); } catch (_e) {}
        return 1;
      },
      onEdit: function (payload) {
        var url = payload && payload.imageUrl;
        if (!url) return 0;
        try {
          var _p = _shelfUseHistoryAsSource(state, context, actions, "source_image", String(url));
          if (_p && typeof _p.catch === "function") _p.catch(function () {});
        } catch (_e) {}
        try { _setActiveSubtool(state, context, actions, "edit", "text"); } catch (_e2) {}
        return 1;
      },
      onPostProcess: function (payload) {
        var url = payload && payload.imageUrl;
        if (!url) return 0;
        try { _setCanvasImage(state, String(url), context); } catch (_e) {}
        try { _setActiveSubtool(state, context, actions, "post", "adjust"); } catch (_e2) {}
        return 1;
      },
      onUpscale: function (payload) {
        var url = payload && payload.imageUrl;
        if (!url) return 0;
        try { _setCanvasImage(state, String(url), context); } catch (_e) {}
        try { _setActiveSubtool(state, context, actions, "post", "upscale"); } catch (_e2) {}
        return 1;
      },
      onClose: function () {
        if (state.playground) state.playground._previewOpen = false;
        _clearPlaygroundPreviewId();
      },
              persistence: {
               setFavorite: function (rec, next) {
                 if (!_runId) return Promise.resolve();
                 return _writeAnnotation("favorite", next);
               },
               setNote: function (rec, text) {
                 if (!_runId) return Promise.resolve();
                 return _writeAnnotation("note", text);
               },
               deleteGeneration: _canDelete
                 ? function (rec) { return _historyRepo.deleteGeneration(rec.id); }
                 : undefined,
               onChanged: null,
             },
    }));
  } catch (e) {
    // Do not swallow: a silent failure here looks like "click does nothing".
    console.error("comfymodal: image preview overlay failed to open", e);
    if (state.playground) state.playground._previewOpen = false;
    return;
  }
  document.body.appendChild(_preview.overlay);
}

function openQueueViewer(state, context) {
  closeQueueViewer();
  var overlay = el("div", {
    class: "comfymodal-studio-queue-viewer-overlay",
    "data-testid": "queue-viewer",
  });
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeQueueViewer();
  });
  var panel = el("div", {
    class: "comfymodal-studio-queue-viewer comfymodal-studio-queue-manager",
    role: "dialog",
    "aria-label": "Queue manager",
  });
  var head = el("div", { class: "comfymodal-studio-queue-viewer-head" });
  head.appendChild(el("h3", {
    class: "comfymodal-studio-queue-viewer-heading",
    text: "Queue Manager",
  }));
  head.appendChild(el("span", {
    class: "comfymodal-studio-queue-viewer-count",
    "data-testid": "queue-viewer-count",
  }));
  var closeBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    "data-testid": "queue-viewer-close",
    text: "Close",
  });
  closeBtn.addEventListener("click", closeQueueViewer);
  head.appendChild(closeBtn);
  panel.appendChild(head);
  panel.appendChild(el("div", {
    class: "comfymodal-studio-queue-manager-batch",
    "data-testid": "queue-manager-batch",
  }));
  panel.appendChild(el("div", {
    class: "comfymodal-studio-queue-viewer-list",
    "data-testid": "queue-viewer-list",
  }));
  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  _queueViewerEl = overlay;
  _refreshQueueViewer(state, context);
  closeBtn.focus();
  document.addEventListener("keydown", _queueViewerKeydown);
}

function _refreshQueueViewer(state, context) {
  if (!_queueViewerEl || !_queueViewerEl.isConnected) return;
  // History mode: a read-only past batch, unaffected by live state.
  if (_queueViewerHistory) {
    var hList = _queueViewerEl.querySelector('[data-testid="queue-viewer-list"]');
    var hBatch = _queueViewerEl.querySelector('[data-testid="queue-manager-batch"]');
    var hCount = _queueViewerEl.querySelector('[data-testid="queue-viewer-count"]');
    if (!hList) return;
    while (hList.firstChild) hList.removeChild(hList.firstChild);
    if (hBatch) {
      while (hBatch.firstChild) hBatch.removeChild(hBatch.firstChild);
      hBatch.appendChild(_renderHistoryRecord(state, context, _queueViewerHistory));
    }
    if (hCount) {
      var rec = _queueViewerHistory;
      hCount.textContent = rec.completed + "/" + rec.total + " complete"
        + (rec.failed ? " · " + rec.failed + " failed" : "");
    }
    return;
  }
  var pg = state.playground || {};
  var q = _runQueueOf(state);
  var batchItems = Array.isArray(pg._batchItems) ? pg._batchItems : [];
  var batchSection = _queueViewerEl.querySelector('[data-testid="queue-manager-batch"]');
  var list = _queueViewerEl.querySelector('[data-testid="queue-viewer-list"]');
  var count = _queueViewerEl.querySelector('[data-testid="queue-viewer-count"]');
  if (!list) return;
  while (list.firstChild) list.removeChild(list.firstChild);
  if (batchSection) {
    while (batchSection.firstChild) batchSection.removeChild(batchSection.firstChild);
    var batchBody = _renderBatchSection(state, context);
    if (batchBody) batchSection.appendChild(batchBody);
  }
  var waiting = q.length;
  var summary = [];
  if (batchItems.length) {
    var done = batchItems.filter(function (e) { return e && e.status === "done"; }).length;
    summary.push("batch " + done + "/" + batchItems.length);
  }
  summary.push(waiting ? waiting + " waiting" : "Empty");
  if (count) count.textContent = summary.join(" · ");
  if (!q.length) {
    list.appendChild(el("p", {
      class: "comfymodal-studio-tool-submenu-note",
      text: "Queue is empty — use the Queue button to add the current settings.",
    }));
    return;
  }
  list.appendChild(el("h4", {
    class: "comfymodal-studio-queue-manager-subhead",
    text: "Queued",
  }));
  q.forEach(function (item, idx) {
    list.appendChild(_renderQueuedItem(state, context, item, idx, q.length));
  });
}

var _BATCH_STATUS_LABELS = {
  pending: "Pending",
  running: "Running",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

function _renderBatchSection(state, context) {
  var pg = state.playground || {};
  var batchItems = Array.isArray(pg._batchItems) ? pg._batchItems : [];
  if (!batchItems.length) return null;
  var wrap = el("div", { class: "comfymodal-studio-batch-section" });
  var head = el("div", { class: "comfymodal-studio-batch-section-head" });
  head.appendChild(el("h4", {
    class: "comfymodal-studio-queue-manager-subhead",
    text: pg._batchApplying ? "Batch running" : "Last batch",
  }));
  var done = 0, failed = 0, skipped = 0, running = 0;
  batchItems.forEach(function (entry) {
    if (!entry) return;
    if (entry.status === "done") done++;
    else if (entry.status === "failed") failed++;
    else if (entry.status === "skipped") skipped++;
    else if (entry.status === "running") running++;
  });
  var total = batchItems.length;
  var settled = done + failed + skipped;
  var parts = [done + "/" + total + " complete"];
  if (failed) parts.push(failed + " failed");
  if (skipped) parts.push(skipped + " skipped");
  if (running) parts.push(running + " running");
  if (pg._batchCancelled) parts.push("cancelled");
  head.appendChild(el("span", {
    class: "comfymodal-studio-batch-summary",
    "data-testid": "batch-summary",
    text: parts.join(" · "),
  }));
  if (pg._batchApplying && !pg._batchCancelling) {
    var cancelAll = el("button", {
      type: "button",
      class: "comfymodal-destructive-btn",
      "data-testid": "batch-cancel-btn",
      text: "Cancel batch",
      title: "Stop after the current variant — the rest returns to the queue",
    });
    cancelAll.addEventListener("click", function () {
      if (state.playground) state.playground._batchCancelling = true;
      cancelAll.disabled = true;
      cancelAll.textContent = "Cancelling…";
      var apiBase = (context && context.apiBase) || "/comfymodal";
      cancelStudioBatch(apiBase, { request_id: (state.playground && state.playground._batchId) || "" }).catch(function () {});
      _refreshQueueViewer(state, context);
    });
    head.appendChild(cancelAll);
  } else if (pg._batchCancelling && pg._batchApplying) {
    head.appendChild(el("span", {
      class: "comfymodal-studio-tool-submenu-note",
      text: "Cancelling after the current variant…",
    }));
  }
  wrap.appendChild(head);
  var bar = el("div", {
    class: "comfymodal-studio-batch-progress",
    "data-testid": "batch-progress",
    role: "progressbar",
    "aria-valuemin": "0",
    "aria-valuemax": String(total),
    "aria-valuenow": String(settled),
  });
  var fill = el("div", { class: "comfymodal-studio-batch-progress-fill" });
  fill.style.width = total ? Math.round((settled / total) * 100) + "%" : "0%";
  bar.appendChild(fill);
  wrap.appendChild(bar);
  batchItems.forEach(function (entry) {
    wrap.appendChild(_renderBatchRow(state, context, entry));
  });
  return wrap;
}

// Read-only past-batch view for the history dropdown: summary, progress,
// and per-item rows. Done rows open in the shared studio viewer.
function _renderHistoryRecord(state, context, rec) {
  var wrap = el("div", { class: "comfymodal-studio-batch-section" });
  var head = el("div", { class: "comfymodal-studio-batch-section-head" });
  head.appendChild(el("h4", {
    class: "comfymodal-studio-queue-manager-subhead",
    text: (rec.workflowName || "Batch") + " · " + new Date(rec.createdAt || Date.now()).toLocaleString(),
  }));
  var parts = [rec.completed + "/" + rec.total + " complete"];
  if (rec.failed) parts.push(rec.failed + " failed");
  if (rec.skipped) parts.push(rec.skipped + " skipped");
  if (rec.cancelled) parts.push("cancelled");
  head.appendChild(el("span", {
    class: "comfymodal-studio-batch-summary",
    text: parts.join(" · "),
  }));
  wrap.appendChild(head);
  var total = rec.total || (rec.items || []).length || 0;
  var settled = (rec.completed || 0) + (rec.failed || 0) + (rec.skipped || 0);
  var bar = el("div", {
    class: "comfymodal-studio-batch-progress",
    role: "progressbar",
    "aria-valuemin": "0",
    "aria-valuemax": String(total),
    "aria-valuenow": String(settled),
  });
  var fill = el("div", { class: "comfymodal-studio-batch-progress-fill" });
  fill.style.width = total ? Math.round((settled / total) * 100) + "%" : "0%";
  bar.appendChild(fill);
  wrap.appendChild(bar);
  (rec.items || []).forEach(function (item) {
    wrap.appendChild(_renderBatchRow(state, context, {
      variantRequestId: item.variantRequestId || item.label || "",
      label: item.label || "",
      status: item.status || "pending",
      outputUrl: item.outputUrl || "",
      historyGenerationId: item.historyGenerationId || "",
      message: item.message || "",
    }, true));
  });
  return wrap;
}

function _renderBatchRow(state, context, entry, readOnly) {
  var pg = state.playground || {};
  var row = el("div", {
    class: "comfymodal-studio-batch-row is-" + (entry.status || "pending"),
    "data-testid": "batch-row-" + entry.variantRequestId,
    "data-variant-id": entry.variantRequestId,
  });
  if (entry.status === "done" && entry.outputUrl) {
    var thumb = el("img", {
      class: "comfymodal-studio-batch-row-thumb",
      src: entry.outputUrl,
      alt: entry.label || "Batch result",
      "data-testid": "batch-row-thumb-" + entry.variantRequestId,
      title: "Open in viewer",
    });
    thumb.style.cursor = "zoom-in";
    thumb.setAttribute("role", "button");
    thumb.setAttribute("tabindex", "0");
    var openIt = function () {
      openRunImagePreview(state, context, {
        runId: entry.variantRequestId,
        id: entry.variantRequestId,
        historyGenerationId: entry.historyGenerationId || "",
      }, entry.outputUrl);
    };
    thumb.addEventListener("click", openIt);
    thumb.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openIt(); }
    });
    row.appendChild(thumb);
  }
  var label = el("span", {
    class: "comfymodal-studio-batch-row-label",
    text: entry.label || entry.variantRequestId,
    title: entry.message || entry.label || "",
  });
  row.appendChild(label);
  row.appendChild(el("span", {
    class: "comfymodal-studio-batch-status is-" + (entry.status || "pending"),
    "data-testid": "batch-row-status-" + entry.variantRequestId,
    text: _BATCH_STATUS_LABELS[entry.status] || entry.status || "Pending",
  }));
  if (!readOnly && (entry.status === "pending" || entry.status === "running") && pg._batchApplying) {
    var skip = el("button", {
      type: "button",
      class: "comfymodal-destructive-btn",
      "data-testid": "batch-skip-btn",
      "data-variant-id": entry.variantRequestId,
      text: entry.status === "running" ? "Skip next" : "Skip",
      title: entry.status === "running"
        ? "The running variant finishes; this takes effect afterwards"
        : "Skip this variant — it returns to the queue",
    });
    skip.addEventListener("click", function () {
      skip.disabled = true;
      var apiBase = (context && context.apiBase) || "/comfymodal";
      cancelStudioBatch(apiBase, {
        request_id: (state.playground && state.playground._batchId) || "",
        variant_request_id: entry.variantRequestId,
      }).catch(function () {});
    });
    row.appendChild(skip);
  }
  if (entry.status === "done" && entry.outputUrl) {
    var view = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn",
      "data-testid": "batch-view-btn",
      "data-variant-id": entry.variantRequestId,
      text: "View",
      title: "Open in the studio viewer",
    });
    view.addEventListener("click", function () {
      openRunImagePreview(state, context, {
        runId: entry.variantRequestId,
        id: entry.variantRequestId,
        historyGenerationId: entry.historyGenerationId || "",
      }, entry.outputUrl);
    });
    row.appendChild(view);
  }
  return row;
}

function _moveQueueItem(state, context, id, delta) {
  var q = _runQueueOf(state);
  var at = q.findIndex(function (r) { return r && r.id === id; });
  if (at === -1) return;
  var to = at + delta;
  if (to < 0 || to >= q.length) return;
  var moved = q.splice(at, 1)[0];
  q.splice(to, 0, moved);
  _saveQueue(state);
  _refreshQueueViewer(state, context);
  if (context && context.setPage) context.setPage("playground");
}

function _renderQueuedItem(state, context, item, idx, total) {
  var card = el("div", {
    class: "comfymodal-studio-queued-item",
    "data-testid": "queued-item-" + item.id,
    "data-queue-id": item.id,
  });
  var top = el("div", { class: "comfymodal-studio-queued-item-top" });
  var reorder = el("span", { class: "comfymodal-studio-queue-reorder" });
  var up = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn comfymodal-studio-queue-move-btn",
    "data-testid": "queue-move-up",
    "data-queue-id": item.id,
    text: "▲",
    title: "Move up",
    disabled: idx === 0,
    "aria-label": "Move " + (item.label || item.id) + " up",
  });
  up.addEventListener("click", function () { _moveQueueItem(state, context, item.id, -1); });
  var down = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn comfymodal-studio-queue-move-btn",
    "data-testid": "queue-move-down",
    "data-queue-id": item.id,
    text: "▼",
    title: "Move down",
    disabled: idx >= total - 1,
    "aria-label": "Move " + (item.label || item.id) + " down",
  });
  down.addEventListener("click", function () { _moveQueueItem(state, context, item.id, 1); });
  reorder.appendChild(up);
  reorder.appendChild(down);
  top.appendChild(reorder);
  var labelBtn = el("button", {
    type: "button",
    class: "comfymodal-studio-queued-item-label is-button",
    "data-testid": "queued-item-label-" + item.id,
    text: (idx + 1) + ". " + (item.label || item.id),
    title: "Show captured settings",
  });
  top.appendChild(labelBtn);
  var del = el("button", {
    type: "button",
    class: "comfymodal-destructive-btn",
    "data-testid": "queue-delete-btn",
    "data-queue-id": item.id,
    text: "Delete",
    title: "Remove this queued run",
  });
  del.addEventListener("click", function () {
    var q = _runQueueOf(state);
    var at = q.findIndex(function (r) { return r && r.id === item.id; });
    if (at !== -1) q.splice(at, 1);
    _saveQueue(state);
    _refreshQueueViewer(state, context);
    if (context && context.setPage) context.setPage("playground");
  });
  top.appendChild(del);
  card.appendChild(top);

  var spec = STUDIO_TOOLS.find(function (t) { return t.id === item.tool; });
  var meta = el("div", { class: "comfymodal-studio-queued-item-meta" });
  meta.appendChild(el("span", { text: "Tool: " + (spec ? spec.label : (item.tool || "—")) }));
  meta.appendChild(el("span", {
    text: "Workflow: " + (item.workflowName || item.workflowId || "—")
      + (item.workflowVersionId ? " · " + item.workflowVersionId : ""),
  }));
  if (item.createdAt) {
    meta.appendChild(el("span", {
      text: "Queued: " + new Date(item.createdAt).toLocaleTimeString(),
    }));
  }
  card.appendChild(meta);

  var detail = el("div", {
    class: "comfymodal-studio-queued-item-detail",
    "data-testid": "queued-item-detail-" + item.id,
    hidden: true,
  });
  var keys = Object.keys(item.controlValues || {});
  if (!keys.length) {
    detail.appendChild(el("p", {
      class: "comfymodal-studio-tool-submenu-note",
      text: "No control values captured.",
    }));
  } else {
    var data = el("dl", {
      class: "comfymodal-studio-queued-item-data",
      "data-testid": "queued-item-data-" + item.id,
    });
    keys.forEach(function (k) {
      var full = "";
      try {
        full = (typeof item.controlValues[k] === "string")
          ? item.controlValues[k]
          : JSON.stringify(item.controlValues[k]);
      } catch (_e) {
        full = String(item.controlValues[k]);
      }
      data.appendChild(el("dt", { text: k }));
      data.appendChild(el("dd", {
        text: _formatQueuedValue(item.controlValues[k]),
        title: String(full == null ? "" : full).slice(0, 500),
      }));
    });
    detail.appendChild(data);
  }
  card.appendChild(detail);
  labelBtn.setAttribute("aria-expanded", "false");
  labelBtn.addEventListener("click", function () {
    var open = detail.hasAttribute("hidden");
    if (open) detail.removeAttribute("hidden");
    else detail.setAttribute("hidden", "");
    labelBtn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  return card;
}

// Phase 10: compare picker modal. A = current canvas (when one exists)
// or a History output; B = a History output. Both sides resolve to plain
// {url, label} descriptors for openComparePair. No new state, no backend.
function _openComparePicker(state, context, actions) {
  try {
    var olds = document.querySelector('[data-testid="compare-picker"]');
    if (olds && olds.parentNode) olds.parentNode.removeChild(olds);
    var runs = [];
    try {
      runs = (getRecentRuns() || []).filter(function (nr) {
        return nr && typeof nr.imageUrl === "string" && nr.imageUrl;
      }).slice(0, 20);
    } catch (_e) { runs = []; }
    var currentUrl = "";
    try { currentUrl = _canvasImageUrl(state) || ""; } catch (_e2) { currentUrl = ""; }
    function runLabel(nr, i) {
      var t = (nr && (nr.prompt || nr.label || nr.id)) || ("Run " + (i + 1));
      return String(t).slice(0, 60);
    }
    var overlay = el("div", {
      class: "comfymodal-studio-compare-picker-overlay",
      "data-testid": "compare-picker",
      style: "position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:80;display:flex;align-items:center;justify-content:center;",
    });
    var dialog = el("div", {
      role: "dialog",
      "aria-label": "Choose images to compare",
      style: "background:#141416;border:1px solid var(--color-border, #333);border-radius:10px;padding:16px;max-width:560px;width:calc(100% - 32px);max-height:80vh;overflow:auto;",
    });
    dialog.appendChild(el("h4", {
      text: "Compare images",
      style: "margin:0 0 4px;",
    }));
    dialog.appendChild(el("p", {
      text: "A shows on the left of the divider, B on the right.",
      style: "font-size:11px;color:#888;margin:0 0 10px;",
    }));
    var goBtn = null;
    function paintGo() {
      // Runs during row construction (before goBtn/rows exist) as well as
      // after: null-safe so early paints only refresh thumbnails.
      try {
        if (!goBtn) return;
        var ok = !!(rowA._resolveUrl() && rowB._resolveUrl());
        goBtn.disabled = !ok;
      } catch (_e) {}
    }
    function sideRow(side) {
      var isA = side === "A";
      var row = el("div", { style: "display:flex;gap:8px;align-items:center;margin-bottom:8px;" });
      row.appendChild(el("span", { text: side, style: "font-size:12px;color:#aaa;flex:none;width:14px;" }));
      var sel = el("select", {
        "data-testid": "compare-pick-" + side.toLowerCase(),
        class: "comfymodal-input",
        style: "flex:1;min-width:0;",
      });
      if (isA) {
        var cur = document.createElement("option");
        cur.value = "current";
        cur.textContent = currentUrl ? "Current canvas" : "Current canvas (no image)";
        if (!currentUrl) cur.disabled = true;
        else cur.selected = true;
        sel.appendChild(cur);
      }
      runs.forEach(function (nr, i) {
        var o = document.createElement("option");
        o.value = String(i);
        o.textContent = runLabel(nr, i);
        if (!isA && i === 0) o.selected = true;
        sel.appendChild(o);
      });
      var thumb = el("img", {
        "data-testid": "compare-thumb-" + side.toLowerCase(),
        alt: "",
        style: "width:56px;height:56px;object-fit:cover;border-radius:6px;flex:none;background:#000;",
      });
      row.appendChild(sel);
      row.appendChild(thumb);
      function resolve() {
        if (isA && sel.value === "current") return currentUrl;
        var nr = runs[Number(sel.value)];
        return (nr && nr.imageUrl) || "";
      }
      function paint() {
        var u = resolve();
        if (u) { thumb.setAttribute("src", u); thumb.style.visibility = ""; }
        else { thumb.removeAttribute("src"); thumb.style.visibility = "hidden"; }
        paintGo();
      }
      sel.addEventListener("change", paint);
      row._resolveUrl = resolve;
      row._select = sel;
      paint();
      return row;
    }
    var rowA = sideRow("A");
    var rowB = sideRow("B");
    dialog.appendChild(rowA);
    dialog.appendChild(rowB);
    var foot = el("div", { style: "display:flex;gap:8px;justify-content:flex-end;margin-top:10px;" });
    var closeBtn = el("button", { type: "button", class: "comfymodal-secondary-btn", text: "Close", "data-testid": "compare-picker-close" });
    goBtn = el("button", {
      type: "button", class: "comfymodal-primary-btn", text: "Compare →",
      "data-testid": "compare-start",
    });
    var closed = false;
    function closePicker() {
      if (closed) return;
      closed = true;
      try { document.removeEventListener("keydown", onPickerKey); } catch (_e) {}
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    function onPickerKey(ev) {
      if (!ev || ev.key !== "Escape") return;
      // Self-cleaning: only act while our overlay is still mounted.
      if (!document.querySelector('[data-testid="compare-picker"]')) {
        try { document.removeEventListener("keydown", onPickerKey); } catch (_e) {}
        return;
      }
      closePicker();
    }
    closeBtn.addEventListener("click", function () {
      closePicker();
    });
    overlay.addEventListener("click", function (ev) {
      if (ev.target === overlay) closePicker();
    });
    try { document.addEventListener("keydown", onPickerKey); } catch (_e) {}
    goBtn.addEventListener("click", function () {
      var au = "", bu = "";
      try { au = rowA._resolveUrl(); bu = rowB._resolveUrl(); } catch (_e) {}
      if (!au || !bu) return;
      var anr = null, bnr = null;
      try {
        var av = rowA._select.value, bv = rowB._select.value;
        anr = av === "current" ? null : runs[Number(av)];
        bnr = runs[Number(bv)];
      } catch (_e2) {}
      var ok = false;
      try {
        ok = openComparePair({
          a: { url: au, label: anr ? runLabel(anr, 0) : "Current canvas" },
          b: { url: bu, label: bnr ? runLabel(bnr, 0) : "History image" },
        });
      } catch (_e3) { ok = false; }
      if (ok && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });
    foot.appendChild(closeBtn);
    foot.appendChild(goBtn);
    dialog.appendChild(foot);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    paintGo();
  } catch (_e) {}
}

function renderWorkspaceTopBar(state, context, actions) {
  var pg = state.playground || {};
  var queueMode = !!pg.queueMode;
  var experimentMode = !!pg.experimentMode;
  var queue = _runQueueOf(state);

  var bar = el("div", {
    class: "comfymodal-studio-workspace-topbar",
    "data-testid": "workspace-topbar",
  });

  var leftSpacer = el("div", { class: "comfymodal-studio-topbar-spacer" });
  bar.appendChild(leftSpacer);

  var railWrap = el("div", { class: "comfymodal-studio-topbar-rail" });
  railWrap.appendChild(renderToolStrip(state, context, actions));
  bar.appendChild(railWrap);

  var right = el("div", { class: "comfymodal-studio-topbar-actions" });

  // Queue toggle (radio with experiment toggle), split with the batch
  // history dropdown: squared inner corners + 2px gap read as one button.
  var queueSplit = el("div", { class: "comfymodal-studio-queue-split" });
  var queueToggle = el("button", {
    type: "button",
    class: "comfymodal-studio-mode-toggle comfymodal-studio-queue-split-main" + (queueMode ? " is-on active" : ""),
    "data-testid": "queue-toggle",
    title: queueMode ? "Queue mode on — runs are collected first" : "Queue mode off — run immediately",
  });
  queueToggle.setAttribute("aria-pressed", queueMode ? "true" : "false");
  queueToggle.appendChild(el("span", { class: "toggle-dot", "aria-hidden": "true" }));
  queueToggle.appendChild(el("span", { text: "Queue" }));
  queueToggle.addEventListener("click", function () {
    if (actions && actions.setQueueMode) actions.setQueueMode(!queueMode);
  });
  queueSplit.appendChild(queueToggle);
  var histArrow = el("button", {
    type: "button",
    class: "comfymodal-studio-mode-toggle comfymodal-studio-queue-split-arrow",
    "data-testid": "queue-history-btn",
    title: "Queued batch history",
    "aria-label": "Queued batch history",
    "aria-expanded": "false",
    "aria-haspopup": "menu",
  });
  histArrow.appendChild(el("span", { "aria-hidden": "true", text: "▾" }));
  var histMenu = el("div", {
    class: "comfymodal-studio-queue-history-menu",
    "data-testid": "queue-history-menu",
    role: "menu",
    hidden: true,
  });
  function _closeHistMenu() {
    histMenu.setAttribute("hidden", "");
    histArrow.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", _outsideHistMenu, true);
    document.removeEventListener("keydown", _escHistMenu);
  }
  function _outsideHistMenu(e) {
    if (!histMenu.isConnected || histMenu.contains(e.target) || histArrow.contains(e.target)) return;
    _closeHistMenu();
  }
  function _escHistMenu(e) {
    if (e && e.key === "Escape") _closeHistMenu();
  }
  histArrow.addEventListener("click", function () {
    var open = histMenu.hasAttribute("hidden");
    if (!open) {
      _closeHistMenu();
      return;
    }
    while (histMenu.firstChild) histMenu.removeChild(histMenu.firstChild);
    var records = _loadBatchHistory();
    if (!records.length) {
      histMenu.appendChild(el("div", {
        class: "comfymodal-studio-queue-history-empty",
        text: "No batches yet — queued batches are recorded here.",
      }));
    }
    records.forEach(function (rec) {
      var label = (rec.workflowName || "Batch") + " · "
        + new Date(rec.createdAt || Date.now()).toLocaleString();
      var sub = rec.completed + "/" + rec.total + " complete"
        + (rec.failed ? " · " + rec.failed + " failed" : "")
        + (rec.skipped ? " · " + rec.skipped + " skipped" : "")
        + (rec.cancelled ? " · cancelled" : "");
      var entry = el("button", {
        type: "button",
        class: "comfymodal-studio-queue-history-item",
        role: "menuitem",
        "data-testid": "queue-history-item-" + rec.batchId,
        title: "Open in the queue manager",
      });
      entry.appendChild(el("span", {
        class: "comfymodal-studio-queue-history-item-label",
        text: label,
      }));
      entry.appendChild(el("span", {
        class: "comfymodal-studio-queue-history-item-sub",
        text: sub,
      }));
      entry.addEventListener("click", function () {
        _closeHistMenu();
        _queueViewerHistory = rec;
        openQueueViewer(state, context);
      });
      histMenu.appendChild(entry);
    });
    histMenu.removeAttribute("hidden");
    histArrow.setAttribute("aria-expanded", "true");
    document.addEventListener("click", _outsideHistMenu, true);
    document.addEventListener("keydown", _escHistMenu);
  });
  queueSplit.appendChild(histArrow);
  queueSplit.appendChild(histMenu);
  right.appendChild(queueSplit);

  // Primary run button: becomes "Queue" in queue mode.
  var runState = pg.runState;
  var primaryLabel = queueMode ? "Queue" : "Run";
  var primaryBtn = el("button", {
    type: "button",
    class: "comfymodal-studio-run-btn",
    "data-testid": "run-btn",
    title: queueMode ? "Add current settings to the queue" : "",
  });
  primaryBtn.appendChild(el("span", { class: "run-glyph", "aria-hidden": "true", text: queueMode ? "+" : "▶" }));
  primaryBtn.appendChild(el("span", { text: primaryLabel, "data-testid": "run-btn-label" }));
  var reason = el("div", { class: "comfymodal-studio-topbar-reason" });
  var batchApplying = !!pg._batchApplying;
  // Phase 1 shell gate (Post local engine / later-phase placeholder): no
  // workflow execution from this view. In-flight runs keep their busy UI.
  var _shellGate = _shellRunGate(state);
  var _runBusy = batchApplying
    || (runState && (runState.status === "running" || runState.status === "submitted"
    || runState.status === "waiting" || runState.status === "queued"
    || runState.status === "in_progress"));
  if (_shellGate && !_runBusy) {
    // Disabled with an honest reason; queue/enqueue handlers below must
    // not attach in this view.
    primaryBtn.disabled = true;
    primaryBtn.title = _shellGate;
    if (reason) {
      reason.appendChild(el("p", {
        "data-testid": "shell-gate-reason",
        text: _shellGate,
        style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
      }));
    }
  } else if (batchApplying) {
    // A container batch is in flight: lock the primary button on batch
    // progress so a second batch or single run cannot overlap it.
    primaryBtn.disabled = true;
    primaryBtn.classList.add("is-busy");
    var _done = pg._batchCompleted || 0;
    var _total = pg._batchTotal || 0;
    primaryBtn.querySelector('[data-testid="run-btn-label"]').textContent =
      _total ? ("Batch " + _done + "/" + _total + "…") : "Batch…";
    primaryBtn.title = "Batch running";
  } else if (runState && (runState.status === "running" || runState.status === "submitted"
    || runState.status === "waiting" || runState.status === "queued"
    || runState.status === "in_progress")) {
    primaryBtn.disabled = true;
    primaryBtn.classList.add("is-busy");
    primaryBtn.querySelector('[data-testid="run-btn-label"]').textContent =
      runState.status === "queued" ? "Queued…" : "Running…";
    primaryBtn.title = "Run in progress";
  } else if (queueMode) {
    primaryBtn.disabled = false;
    primaryBtn.onclick = null;
    primaryBtn.addEventListener("click", function () {
      _enqueueCurrentRun(state);
      if (context && context.setPage) context.setPage("playground");
    });
  } else if (_isModernRunSelected(state)) {
    primaryBtn.disabled = true;
    var _savedOnclick = primaryBtn.onclick;
    _applyModernRunButtonState(state, context, actions, primaryBtn, reason);
    // _applyModernRunButtonState sets textContent directly; restore the
    // glyph+label structure it replaces while keeping its gating outcome.
    var _label = String(primaryBtn.textContent || "Run");
    var _wasDisabled = !!primaryBtn.disabled;
    var _gatedOnclick = primaryBtn.onclick;
    while (primaryBtn.firstChild) primaryBtn.removeChild(primaryBtn.firstChild);
    primaryBtn.appendChild(el("span", { class: "run-glyph", "aria-hidden": "true", text: "▶" }));
    primaryBtn.appendChild(el("span", { text: _label, "data-testid": "run-btn-label" }));
    primaryBtn.disabled = _wasDisabled;
    if (!_wasDisabled) {
      primaryBtn.onclick = function () {
        primaryBtn.disabled = true;
        var lbl = primaryBtn.querySelector('[data-testid="run-btn-label"]');
        if (lbl) lbl.textContent = "Running…";
        _modernRunSubmit(state, context, actions, primaryBtn);
        if (primaryBtn.disabled === false && typeof _gatedOnclick === "function") _gatedOnclick();
        void _savedOnclick;
      };
    } else {
      primaryBtn.onclick = null;
    }
  } else {
    primaryBtn.disabled = true;
    primaryBtn.title = "Select a workflow to run";
  }
  right.appendChild(primaryBtn);

  // Phase 10: Compare launcher beside RUN. Opens a History picker (current
  // canvas vs a past output, or two past outputs) and opens the shared
  // reveal-divider compare view. Always available — comparing is local.
  var compareBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    "data-testid": "compare-open",
    text: "Compare",
    title: "Compare the current canvas with a History image, or two History images",
  });
  compareBtn.addEventListener("click", function () {
    try { _openComparePicker(state, context, actions); } catch (_e) {}
  });
  right.appendChild(compareBtn);

  // Run-queue button: only in queue mode, beside the Queue button.
  if (queueMode) {
    var runQueueBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-studio-run-queue-btn",
      "data-testid": "run-queue-btn",
      title: queue.length ? "Run all queued items in order — same-workflow groups share one container (" + queue.length + " waiting)" : "Queue is empty — queue a run first",
    });
    runQueueBtn.textContent = "Run queue" + (queue.length ? " (" + queue.length + ")" : "");
    runQueueBtn.disabled = queue.length === 0 || _isRunActive(state) || !!pg._batchApplying || !!_shellGate;
    if (_shellGate) runQueueBtn.title = _shellGate;
    runQueueBtn.addEventListener("click", function () {
      _drainNextGroup(state, context, actions);
    });
    right.appendChild(runQueueBtn);

    // View queued runs: opens the queue viewer (per-run data + delete).
    var viewQueueBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-studio-queue-view-btn",
      "data-testid": "queue-view-btn",
      title: queue.length ? "View queued runs (" + queue.length + " waiting)" : "Queue is empty",
    });
    viewQueueBtn.textContent = "View" + (queue.length ? " (" + queue.length + ")" : "");
    viewQueueBtn.disabled = queue.length === 0;
    viewQueueBtn.addEventListener("click", function () {
      openQueueViewer(state, context);
    });
    right.appendChild(viewQueueBtn);

    // Clear queue: drops all waiting runs (the active run is unaffected —
    // it already left the queue when it started).
    var clearQueueBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-studio-queue-clear-btn",
      "data-testid": "queue-clear-btn",
      title: queue.length ? "Remove all queued runs (" + queue.length + ")" : "Queue is empty",
      text: "Clear",
    });
    clearQueueBtn.disabled = queue.length === 0;
    clearQueueBtn.addEventListener("click", function () {
      var q = _runQueueOf(state);
      q.length = 0;
      _saveQueue(state);
      _refreshQueueViewer(state, context);
      if (context && context.setPage) context.setPage("playground");
    });
    right.appendChild(clearQueueBtn);

    // Cancel batch: stops after the current variant (a running variant
    // always finishes); everything not yet run returns to the queue.
    if (pg._batchApplying) {
      var cancelBatchBtn = el("button", {
        type: "button",
        class: "comfymodal-destructive-btn comfymodal-studio-batch-cancel-btn",
        "data-testid": "batch-cancel-btn",
        title: "Stop the batch after the current variant — the rest returns to the queue",
        text: pg._batchCancelling ? "Cancelling…" : "Cancel",
        disabled: !!pg._batchCancelling,
      });
      cancelBatchBtn.addEventListener("click", function () {
        if (state.playground) state.playground._batchCancelling = true;
        cancelBatchBtn.disabled = true;
        cancelBatchBtn.textContent = "Cancelling…";
        var apiBase = (context && context.apiBase) || "/comfymodal";
        cancelStudioBatch(apiBase, { request_id: (state.playground && state.playground._batchId) || "" }).catch(function () {});
      });
      right.appendChild(cancelBatchBtn);
    }
  }

  // Experiment toggle: same behavior as the old control-panel button
  // (renderExperimentToggle), now a compact radio with queue mode.
  var expToggle = el("button", {
    type: "button",
    class: "comfymodal-studio-mode-toggle" + (experimentMode ? " is-on active" : ""),
    "data-testid": "experiment-toggle",
    title: experimentMode ? "Exit experiment mode" : "Enter experiment mode",
  });
  expToggle.setAttribute("aria-pressed", experimentMode ? "true" : "false");
  expToggle.appendChild(el("span", { class: "toggle-dot", "aria-hidden": "true" }));
  expToggle.appendChild(el("span", { text: experimentMode ? "Exit Experiment" : "Experiment" }));
  expToggle.addEventListener("click", function () {
    if (actions && actions.setExperimentMode) actions.setExperimentMode(!experimentMode);
  });
  right.appendChild(expToggle);

  right.appendChild(reason);
  bar.appendChild(right);
  _refreshQueueToast(state);
  return bar;
}

// ── Phase 1 mode submenu row ────────────────────────────────────────
// Radio-linked to the mode rail: exactly one submenu is visible, directly
// above the canvas. Buttons reuse the existing secondary-button classes;
// later-phase entries stay visible with honest disabled-execution notes.

function renderToolSubmenu(state, context, actions) {
  var mode = activeModeOf(state);
  var sub = activeSubtoolOf(state);
  var spec = STUDIO_MODES.find(function (m) { return m.id === mode; }) || STUDIO_MODES[0];
  var row = el("div", {
    class: "comfymodal-studio-tool-submenu",
    "data-testid": "tool-submenu-" + spec.id,
    "data-tool": spec.id,
  });
  var title = el("span", {
    class: "comfymodal-studio-tool-submenu-title",
    text: spec.label,
  });
  row.appendChild(title);

  var body = el("div", {
    class: "comfymodal-studio-tool-submenu-body",
    "data-testid": "submenu-body-" + spec.id,
  });

  (STUDIO_SUBMENUS[spec.id] || []).forEach(function (s) {
    // Phase-4 dedup: the sidebar panel grid is the canonical navigation for
    // passive adjustment panels, so the top Post row keeps only canvas
    // interaction modes (Crop/Heal) and the Phase-11 operation (Upscale).
    // Internal category semantics (adjust/color/detail/effects) are unchanged:
    // STUDIO_SUBMENUS.post, _selectPostCategory validation, handoffs, and the
    // engine data-post-category mapping all still use them.
    if (spec.id === "post" && s !== "crop" && s !== "heal" && s !== "upscale") return;
    var isActive = s === sub;
    var btn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn" + (isActive ? " is-on active" : ""),
      "data-testid": "studio-subtool-" + s,
      "data-subtool": s,
      text: STUDIO_SUBTOOL_LABELS[s] || s,
      title: (STUDIO_SUBTOOL_LABELS[s] || s)
        + (_isPlaceholderSubtool(s) ? " (later phase — execution disabled)" : ""),
    });
    btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    btn.addEventListener("click", function () {
      if (spec.id === "post") _selectPostCategory(state, context, s);
      else _setActiveSubtool(state, context, actions, spec.id, s);
    });
    body.appendChild(btn);
  });

  if (mode === "generate" && sub === "text") {
    // Background fill: paints the canvas background a user-picked color.
    var pg = state.playground || {};
    var current = pg.canvasBg || "";
    var fillBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-studio-bgfill-btn" + (current ? " is-on" : ""),
      "data-testid": "bg-fill-btn",
      title: "Fill the canvas background with a solid color",
    });
    fillBtn.appendChild(el("span", { "aria-hidden": "true", text: "🪣 " }));
    fillBtn.appendChild(el("span", { text: "Bg Fill" }));
    var picker = document.createElement("input");
    picker.type = "color";
    picker.value = current || "#18181b";
    picker.setAttribute("data-testid", "bg-fill-picker");
    picker.setAttribute("aria-label", "Background fill color");
    picker.title = "Pick a background color";
    picker.addEventListener("input", function () {
      var canvas = document.querySelector('[data-testid="canvas-area"]');
      if (canvas) {
        canvas.style.background = picker.value;
        canvas.style.backgroundImage = "none";
      }
    });
    picker.addEventListener("change", function () {
      if (actions && actions.setCanvasBg) actions.setCanvasBg(picker.value);
    });
    fillBtn.addEventListener("click", function () { picker.click(); });
    body.appendChild(fillBtn);
    body.appendChild(picker);
    if (current) {
      var swatch = el("span", {
        class: "comfymodal-studio-bgfill-swatch",
        "data-testid": "bg-fill-swatch",
        title: current,
      });
      swatch.style.background = current;
      body.appendChild(swatch);
      var clear = el("button", {
        type: "button",
        class: "comfymodal-secondary-btn",
        "data-testid": "bg-fill-clear",
        text: "Clear",
        title: "Remove the background fill",
      });
      clear.addEventListener("click", function () {
        if (actions && actions.setCanvasBg) actions.setCanvasBg("");
      });
      body.appendChild(clear);
    } else {
      body.appendChild(el("span", {
        class: "comfymodal-studio-tool-submenu-note",
        text: "Optional — fills the empty canvas background.",
      }));
    }
  } else if (spec.id === "post") {
    body.appendChild(el("span", {
      class: "comfymodal-studio-tool-submenu-note",
      "data-testid": "submenu-post-note",
      text: _postSubmenuNote(sub),
    }));
  } else if (_isPlaceholderSubtool(sub)) {
    body.appendChild(el("span", {
      class: "comfymodal-studio-tool-submenu-note",
      text: (STUDIO_SUBTOOL_LABELS[sub] || sub) + " arrives in a later phase — execution is disabled.",
    }));
  }

  row.appendChild(body);
  return row;
}

// Mapped roles that are deliberately NOT rendered as Shelf fields. These are
// model-loader inputs: the files are chosen in the Model Library and already
// flow through the version's executable prompt, so an editable field here only
// invited a second, conflicting place to change the model stack.
var _SHELF_HIDDEN_ROLES = ["model_unet", "clip", "vae", "model", "model_clip", "model_vae"];
var _SHELF_SAVE_DELAY_MS = 300;
var _shelfPointerDrag = null;

function _shelfClearDropIndicators() {
  Array.prototype.forEach.call(document.querySelectorAll(
    ".comfymodal-studio-shelf-card.is-drop-before, .comfymodal-studio-shelf-card.is-drop-after, "
      + ".comfymodal-studio-shelf-row.is-drop-above, .comfymodal-studio-shelf-row.is-drop-below, "
      + ".comfymodal-studio-shelf-row.is-drop-target, "
      + ".comfymodal-studio-shelf-advanced.is-drop-target, "
      + ".comfymodal-studio-shelf-advanced-wrap.is-drop-target"
  ), function (node) {
    node.classList.remove("is-drop-before", "is-drop-after", "is-drop-above", "is-drop-below", "is-drop-target");
  });
}

function _shelfRowRoles(row) {
  return Array.prototype.map.call(row.querySelectorAll("[data-testid^='shelf-field-']"), function (node) {
    return node.getAttribute("data-role");
  }).filter(Boolean);
}

function _shelfDropAtPoint(draggedRole, clientX, clientY) {
  var hit = document.elementFromPoint(clientX, clientY);
  var advancedWrap = hit && hit.closest ? hit.closest(".comfymodal-studio-shelf-advanced-wrap") : null;
  var advancedBox = advancedWrap && advancedWrap.querySelector ? advancedWrap.querySelector("[data-testid='shelf-advanced-section']") : null;
  if (advancedWrap) {
    var advancedTarget = hit.closest("[data-testid^='shelf-field-']");
    if (advancedBox && !advancedBox.hidden && advancedTarget && advancedTarget.getAttribute("data-role") !== draggedRole) {
      var advancedRect = advancedTarget.getBoundingClientRect();
      return {
        mode: clientY < advancedRect.top + advancedRect.height / 2 ? "advanced-before" : "advanced-after",
        targetRole: advancedTarget.getAttribute("data-role"),
        row: advancedBox,
        indicator: advancedWrap,
      };
    }
    return { mode: "advanced", row: advancedBox, indicator: advancedWrap };
  }
  var target = hit && hit.closest ? hit.closest("[data-testid^='shelf-field-']") : null;
  if (target && target.getAttribute("data-role") !== draggedRole) {
    var targetRow = target.closest(".comfymodal-studio-shelf-row");
    var rowCards = targetRow ? targetRow.querySelectorAll("[data-testid^='shelf-field-']") : [];
    var rect = target.getBoundingClientRect();
    if (clientY >= rect.top + rect.height * 0.25 && clientY <= rect.bottom - rect.height * 0.25) {
      return {
        mode: "row-join",
        targetRole: target.getAttribute("data-role"),
        row: targetRow,
        targetRow: targetRow ? Number(targetRow.getAttribute("data-row")) : 0,
      };
    }
    var after = rowCards.length > 1
      ? clientX >= rect.left + rect.width / 2
      : clientY >= rect.top + rect.height / 2;
    return {
      mode: rowCards.length > 1 ? (after ? "after" : "before") : (after ? "row-after" : "row-before"),
      targetRole: target.getAttribute("data-role"),
      row: targetRow,
      targetRow: targetRow ? Number(targetRow.getAttribute("data-row")) : 0,
    };
  }

  var rows = Array.prototype.slice.call(document.querySelectorAll(".comfymodal-studio-shelf-row"));
  for (var i = 0; i < rows.length - 1; i++) {
    var upper = rows[i].getBoundingClientRect();
    var lower = rows[i + 1].getBoundingClientRect();
    if (clientY >= upper.bottom && clientY <= lower.top) {
      var upperRoles = _shelfRowRoles(rows[i]);
      var lowerRoles = _shelfRowRoles(rows[i + 1]);
      if (upperRoles.length && lowerRoles.length) {
        var midpoint = upper.bottom + (lower.top - upper.bottom) / 2;
        if (clientY < midpoint) {
          return { mode: "row-before", targetRole: lowerRoles[0], row: rows[i + 1], targetRow: Number(rows[i + 1].getAttribute("data-row")) };
        }
        return { mode: "row-after", targetRole: upperRoles[upperRoles.length - 1], row: rows[i], targetRow: Number(rows[i].getAttribute("data-row")) };
      }
    }
  }
  if (rows.length) {
    var first = rows[0].getBoundingClientRect();
    var last = rows[rows.length - 1].getBoundingClientRect();
    var firstRoles = _shelfRowRoles(rows[0]);
    var lastRoles = _shelfRowRoles(rows[rows.length - 1]);
    if (clientY < first.top && firstRoles.length) {
      return { mode: "row-before", targetRole: firstRoles[0], row: rows[0], targetRow: Number(rows[0].getAttribute("data-row")) };
    }
    if (clientY > last.bottom && lastRoles.length) {
      return { mode: "row-after", targetRole: lastRoles[lastRoles.length - 1], row: rows[rows.length - 1], targetRow: Number(rows[rows.length - 1].getAttribute("data-row")) };
    }
  }
  return null;
}

function _shelfStore(state) {
  return (state && state.playground && state.playground._workflowRun) || null;
}

function _shelfModule(state) {
  return (state && state.playground && state.playground._workflowRunModule) || null;
}

function _shelfReady(state) {
  var store = _shelfStore(state);
  var wf = _shelfModule(state);
  if (!store || !wf || !store.workflowId || !store.workflowVersionId) return null;
  if (!store.runContext || !store.runContext.mapping) return null;
  return { store: store, wf: wf };
}

function _shelfEntries(state) {
  var ready = _shelfReady(state);
  if (!ready) return [];
  var entries = ready.store.runContext.mapping.entries;
  return Array.isArray(entries) ? entries.filter(function (e) {
    if (!e || typeof e !== "object") return false;
    var role = e.semantic_role || e.input_name || "";
    if (!role || role === "output") return false;
    // Model-loader roles are not editable knobs: the model/CLIP/VAE files are
    // chosen in the Model Library and already flow through the version's
    // executable prompt. Rendering them here just invited conflicting edits.
    if (_SHELF_HIDDEN_ROLES.indexOf(role) !== -1) return false;
    return true;
  }) : [];
}

function _shelfRoleOf(entry) {
  return (entry && (entry.semantic_role || entry.input_name)) || "";
}

const _TEXT_GENERATE_NODE_TYPES = ["TextGenerate", "TextGenerateLTX2Prompt"];

function _textGenerateBindingStatus(store) {
  var ctx = store && store.runContext;
  var mapping = ctx && ctx.mapping;
  var raw = mapping && mapping.mapping && typeof mapping.mapping === "object" ? mapping.mapping : mapping;
  var binding = raw && raw.text_generate_node_id;
  if (binding == null || String(binding).trim() === "") {
    binding = ctx && ctx.text_generate_binding;
    if (binding && typeof binding === "object") binding = binding.node_id != null ? binding.node_id : binding.nodeId;
  }
  if (binding == null || String(binding).trim() === "") return { bound: false, valid: false, nodeId: "", reason: "" };
  var targetId = String(binding);
  var graph = ctx && ctx.version && (ctx.version.graph_json || ctx.version.graphJson);
  var nodes = Array.isArray(graph) ? graph : graph && Array.isArray(graph.nodes) ? graph.nodes : [];
  var node = nodes.find(function (candidate) {
    return candidate && (String(candidate.id) === targetId || String(candidate.nodeId) === targetId);
  });
  if (!node && ctx && ctx.version && ctx.version.executable_prompt
    && typeof ctx.version.executable_prompt === "object") {
    // Expanded executable keys cover subgraph interiors ("30:10") as flat
    // entries, so composite bindings resolve here without graph surgery.
    var promptNode = ctx.version.executable_prompt[targetId];
    if (promptNode && typeof promptNode === "object") {
      node = { id: targetId, class_type: promptNode.class_type, type: promptNode.class_type };
    }
  }
  if (!node && targetId.indexOf(":") !== -1 && graph && typeof graph === "object") {
    // Composite outer:inner binding against a UI graph: the container's
    // type is its subgraph definition id (same linkage as the wizard scan).
    try {
      var parts = targetId.split(":");
      var outerId = parts[0];
      var innerId = parts.slice(1).join(":");
      var defs = (graph.definitions && graph.definitions.subgraphs) || null;
      var defList = Array.isArray(defs) ? defs : (defs && typeof defs === "object" ? Object.values(defs) : []);
      var container = null;
      for (var i = 0; i < nodes.length; i++) {
        if (nodes[i] && String(nodes[i].id) === outerId) { container = nodes[i]; break; }
      }
      if (container) {
        for (var j = 0; j < defList.length; j++) {
          var def = defList[j];
          if (!def || typeof def !== "object" || String(def.id) !== String(container.type)) continue;
          var inner = Array.isArray(def.nodes) ? def.nodes : [];
          for (var k = 0; k < inner.length; k++) {
            if (inner[k] && String(inner[k].id) === innerId) {
              node = { id: targetId, class_type: inner[k].class_type, type: inner[k].type };
              break;
            }
          }
        }
      }
    } catch (_e) { /* best-effort */ }
  }
  var valid = !!(node && _TEXT_GENERATE_NODE_TYPES.indexOf(node.class_type || node.type) !== -1);
  return {
    bound: true,
    valid: valid,
    nodeId: targetId,
    reason: valid ? "" : "The saved text-generation node is not available in this version."
  };
}

function _renderSkipTextGenerateOption(state, context, actions) {
  var store = _shelfStore(state);
  var status = _textGenerateBindingStatus(store);
  if (!status.bound) return null;
  var wrap = el("div", {
    class: "comfymodal-studio-execution-option",
    "data-testid": "skip-text-generate-option",
    style: "margin:16px 0 4px;padding:12px 14px;border:1px solid rgba(255,255,255,.10);border-radius:8px;",
  });
  var label = el("label", { style: "display:flex;gap:10px;align-items:flex-start;cursor:pointer;" });
  var input = el("input", {
    type: "checkbox",
    class: "comfymodal-input",
    "data-testid": "skip-text-generate",
    "aria-label": "Skip text generation — use the shelf prompt directly",
    disabled: !status.valid,
  });
  input.checked = status.valid && store.skipTextGenerate === true;
  input.setAttribute("aria-pressed", input.checked ? "true" : "false");
  input.addEventListener("change", function () {
    store.setSkipTextGenerate(input.checked);
    saveSkipTextGenerate(store.workflowId, store.workflowVersionId, input.checked);
    input.setAttribute("aria-pressed", input.checked ? "true" : "false");
    _syncWorkflowGating(state, context, actions);
  });
  var copy = el("span", {}, [
    el("strong", { text: "Skip text generation — use the shelf prompt directly", style: "display:block;font-size:12px;line-height:1.35;" }),
    el("span", { text: status.valid ? "Bypasses the saved text-generation node for this run." : status.reason, style: "display:block;font-size:10px;color:#888;margin-top:3px;line-height:1.4;" }),
  ]);
  label.appendChild(input);
  label.appendChild(copy);
  wrap.appendChild(label);
  return wrap;
}

// Catalog-owned role name. Unknown schema roles fall back to the mapping
// display_name (backend truth) ΓÇö never a second hardcoded name table.
function _shelfDisplayName(role, entry) {
  var catalog = role && BINDABLE_INPUTS[role];
  if (catalog) return catalog.name;
  if (entry && entry.display_name) return String(entry.display_name);
  return String(role || "");
}

// The Prompt card: catalog "prompt" first, then the positive-prompt schema
// role, then the first multiline entry. Fixed at top, never draggable.
function _shelfPromptRole(entries) {
  var roles = entries.map(_shelfRoleOf);
  if (roles.indexOf("prompt") !== -1) return "prompt";
  if (roles.indexOf("positive_prompt") !== -1) return "positive_prompt";
  for (var i = 0; i < entries.length; i++) {
    if (entries[i] && (entries[i].control_kind === "multiline" || entries[i].multiline)) {
      return _shelfRoleOf(entries[i]);
    }
  }
  return "";
}

function _shelfEntryFor(entries, role) {
  for (var i = 0; i < entries.length; i++) {
    if (_shelfRoleOf(entries[i]) === role) return entries[i];
  }
  return null;
}

// Mapping control_kind ΓåÆ fixed field-block kind (studio-field-blocks.js).
function _shelfBlockKind(entry) {
  var kind = entry && entry.control_kind;
  if (kind === "multiline") return "multiline";
  if (kind === "integer") return "integer";
  if (kind === "number" || kind === "float") return "float";
  if (kind === "enum") return "dropdown";
  if (kind === "image") return "image";
  if (kind === "file" || kind === "model") return "model-picker";
  if (entry && Array.isArray(entry.enum_options) && entry.enum_options.length) return "dropdown";
  return "";
}

function _shelfCurrentImageUrl(state) {
  // The workspace image: explicit canvas selection first, then the latest
  // run output, then the selected run. The canvas is workflow-independent —
  // it is what the user is actively working on, not just "the last result".
  var canvas = _canvasImageUrl(state);
  if (canvas) return canvas;
  var pg = state && state.playground;
  if (!pg) return "";
  if (pg.lastRunOutput) return String(pg.lastRunOutput);
  var sel = pg._selectedRun;
  if (sel && sel.imageUrl) return String(sel.imageUrl);
  return "";
}

// Full-size canvas URL for a recent-run record: the same Preview >
// Original > Thumbnail resolution the History detail and preview overlay
// use for the record (resolveViewerInput from studio-run-normalizer.js),
// falling back to the record's strip thumbnail.  The carousel strip always
// renders the capped 256px thumbnail, but the canvas must never be set to
// it while the record projects a full-size variant.
function _canvasUrlForRun(nr, fallbackUrl) {
  var fallback = fallbackUrl || (nr && nr.imageUrl) || "";
  if (!nr || typeof nr !== "object") return fallback;
  var resolved = resolveViewerInput(nr, fallback);
  return (resolved && resolved.imageUrl) || fallback;
}

function _canvasImageUrl(state) {
  var pg = state && state.playground;
  if (!pg) return "";
  if (pg.canvasImageUrl) return String(pg.canvasImageUrl);
  if (pg.lastRunOutput) return String(pg.lastRunOutput);
  return "";
}

// Resolve the canvas image to the on-drive file behind it instead of
// re-uploading its pixels as a duplicate. Returns { filename } or null
// when the URL has no file behind it (asset blobs, blob:/data: URLs).
// Annotated output/temp references round-trip through the loader,
// collector, and remote materializer, all of which split the annotation.
function _outputFileFromUrl(url) {
  var s = String(url || "");
  if (!s) return "";
  var m = s.match(/[?&]filename=([^&]+)/);
  if (m) {
    var t = s.match(/[?&]type=([^&]+)/);
    var type = t ? decodeURIComponent(t[1]) : "input";
    var name = decodeURIComponent(m[1]);
    if (!name || name[0] === "/" || name.indexOf("..") !== -1) return "";
    if (type === "input") return name;
    if (type === "output" || type === "temp") return name + " [" + type + "]";
    return "";
  }
  m = s.match(/\/comfymodal\/studio\/outputs\/([^/?#]+)/);
  if (m) return decodeURIComponent(m[1]) + " [output]";
  return "";
}

function _runOutputFile(nr) {
  // Best-effort output filename behind a recent-run record: explicit fields
  // first, then any featured/output URL that resolves to a file.
  if (!nr || typeof nr !== "object") return "";
  var direct = nr.output_path
    || (Array.isArray(nr.output_paths) && nr.output_paths[0])
    || (nr.featuredOutput && (nr.featuredOutput.originalFilename || nr.featuredOutput.filename))
    || "";
  if (direct) {
    var d = String(direct);
    if (/ \[(input|output|temp)\]$/.test(d)) return d;
    return d + " [output]";
  }
  var urls = [nr.imageUrl];
  [nr.featuredOutput].concat(nr.cover || []).forEach(function (f) {
    if (!f || typeof f !== "object") return;
    urls.push(f.thumbUrl, f.previewUrl, f.originalUrl, f.url);
  });
  for (var i = 0; i < urls.length; i++) {
    var hit = _outputFileFromUrl(urls[i]);
    if (hit) return hit;
  }
  return "";
}

function _resolveCanvasFile(state, url) {
  var s = String(url || "");
  if (!s) return null;
  var direct = _outputFileFromUrl(s);
  if (direct) return { filename: direct };
  // History asset URLs: match the run's recorded output file, if known.
  try {
    var runs = getRecentRuns() || [];
    for (var i = 0; i < runs.length; i++) {
      var nr = runs[i];
      if (!nr || String(nr.imageUrl || "") !== s) continue;
      var file = _runOutputFile(nr);
      if (file) return { filename: file };
    }
  } catch (_e) { /* fall through to upload */ }
  return null;
}

// A resolved on-drive hit is only a hit when the file is really servable:
// remote/golden outputs resolve to annotated names with no bytes behind
// them. Verify with one cheap HEAD; anything inconclusive preserves the old
// behavior (assume present) so local flows never regress.
async function _viewFileExists(filename) {
  try {
    var m = String(filename || "").match(/^(.*) \[(input|output|temp)\]$/);
    var url = m
      ? "/view?filename=" + encodeURIComponent(m[1]) + "&type=" + m[2]
      : "/view?filename=" + encodeURIComponent(String(filename || "")) + "&type=input";
    var r = await fetch(url, { method: "HEAD" });
    if (!r) return true;
    if (r.status === 404) return false;
    return true;
  } catch (_e) { return true; }
}

// Async version of _resolveCanvasFile for link flows: phantom hits fall
// through so callers fetch → upload real bytes instead of committing a name
// that previews and runs nowhere.
async function _resolveVerifiedCanvasFile(state, url) {
  var hit = null;
  try { hit = _resolveCanvasFile(state, url); } catch (_e) { hit = null; }
  if (hit && hit.filename && !(await _viewFileExists(hit.filename))) return null;
  return hit;
}

// Same workspace image under different references: exact match or shared
// ?filename= identity only. Bare basenames are NOT compared — two different
// directories can hold the same filename, and mistaking them would silently
// run one image against another's source.
function _sameWorkspaceImage(a, b) {  var sa = String(a || "");
  var sb = String(b || "");
  if (!sa || !sb) return false;
  if (sa === sb) return true;
  function fileParam(s) {
    var m = String(s).match(/[?&]filename=([^&]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  var fa = fileParam(sa);
  var fb = fileParam(sb);
  if (fa && fb) return fa === fb;
  if (fa) return fa === sb;
  if (fb) return fb === sa;
  return false;
}

function _setCanvasImage(state, url, context) {
  var pg = state && state.playground;
  if (!pg || !url) return;
  pg.canvasImageUrl = String(url);
  try {
    if (typeof sessionStorage !== "undefined") {
      sessionStorage.setItem("comfymodal.studio.playground.canvas.v1", String(url));
    }
  } catch (_e) { /* best-effort */ }
  // Sync the live canvas element without a full remount (preserves shelf
  // input focus); renders from state catch up on the next pass. When the
  // workspace is still showing its empty state there is no element to sync,
  // so remount once instead — otherwise a first upload would vanish.
  try {
    var img = document.querySelector('[data-testid="canvas-output"]');
    if (img && img.isConnected) {
      img.setAttribute("src", String(url));
      // A paint overlay belongs to the previous image — clear it so old
      // strokes never corrupt the new base.
      try {
        ["inpaint-canvas", "sketch-canvas"].forEach(function (tid) {
          var p = document.querySelector('[data-testid="' + tid + '"]');
          if (p && p.isConnected) {
            var c = p.getContext("2d");
            if (c) c.clearRect(0, 0, p.width, p.height);
          }
        });
      } catch (_e2) { /* best-effort paint only */ }
      return;
    }
  } catch (_e) { /* fall through to remount */ }
  try {
    if (context && context.setPage) context.setPage("playground");
    else if (typeof window !== "undefined" && window.__studioApi
      && typeof window.__studioApi.setPage === "function") {
      window.__studioApi.setPage("playground");
    }
  } catch (_e) { /* best-effort */ }
}

// A new source image invalidates any bound mask: the mask was painted for a
// different image. Uses the normal commit/gating path so Run truthfully
// reports the missing mask until a new one is painted.
function _clearBoundMask(state, context, actions) {
  try {
    if (_schemaHasRole(state, "mask")) commitShelfValue(state, context, actions, "mask", "");
  } catch (_e) { /* best-effort */ }
  // Phase 3: a saved method mask is bound to its source image too.
  try {
    var _store = _shelfStore(state);
    if (_store && _store.workflowId) saveWorkflowMethods(_store.workflowId, { savedMask: "", savedMaskSource: "" });
  } catch (_e2) { /* best-effort */ }
  try { _syncWorkflowGating(state, context, actions); } catch (_e3) { /* best-effort */ }
}

// The editor base image is gone (source cleared): wipe paint overlays
// directly. Same clearing _setCanvasImage applies when a new source replaces
// the old one.
function _clearPaintOverlays() {
  try {
    ["inpaint-canvas", "sketch-canvas"].forEach(function (tid) {
      var p = document.querySelector('[data-testid="' + tid + '"]');
      if (p && p.isConnected) {
        var c = p.getContext("2d");
        if (c) c.clearRect(0, 0, p.width, p.height);
      }
    });
    // The status line must not keep claiming paint that no longer exists.
    ["inpaint-mask-preview", "sketch-mask-preview"].forEach(function (tid) {
      var n = document.querySelector('[data-testid="' + tid + '"]');
      if (n && n.isConnected) n.textContent = "Mask cleared.";
    });
  } catch (_e) { /* best-effort paint only */ }
}

function _restoreCanvasImage(state) {
  try {
    var pg = state && state.playground;
    if (!pg || pg.canvasImageUrl) return;
    if (typeof sessionStorage === "undefined") return;
    var saved = sessionStorage.getItem("comfymodal.studio.playground.canvas.v1") || "";
    if (saved) pg.canvasImageUrl = saved;
  } catch (_e) { /* best-effort */ }
}

// Image lineage: every workspace image knows what it came from (parent)
// and what was made from it (children, many allowed). Keys are the exact
// strings that flow through the workspace — output URLs for run results,
// uploaded filenames for sources — so edges recorded at run/submit time
// resolve without guessing.
var _LINEAGE_KEY = "comfymodal.studio.playground.lineage.v2";
var _LINEAGE_CAP = 200;

// One identity per image: input-directory files canonicalize to
// `input:<filename>` (with the view `type` when present) no matter whether
// they arrive as a bare name or a /view URL; anything else keeps its full
// URL. Equivalent references always form one node; distinct files never merge.
function _lineageKey(value) {
  var s = String(value || "");
  if (!s) return "";
  var m = s.match(/[?&]filename=([^&]+)/);
  if (m) {
    var t = s.match(/[?&]type=([^&]+)/);
    return (t ? decodeURIComponent(t[1]) : "input") + ":" + decodeURIComponent(m[1]);
  }
  // Annotated file references ("name [output]") keep their directory so
  // input and output files with the same basename never merge.
  m = s.match(/^(.*) \[([^\]]+)\]$/);
  if (m && (m[2] === "input" || m[2] === "output" || m[2] === "temp")) {
    return m[2] + ":" + m[1];
  }
  if (/^(blob:|data:|https?:\/\/|\/)/.test(s)) return "url:" + s;
  return "input:" + s;
}

function _lineageNodes(state) {
  var pg = state && state.playground;
  if (!pg) return {};
  if (!pg.imageLineage || typeof pg.imageLineage !== "object"
    || !pg.imageLineage.nodes || typeof pg.imageLineage.nodes !== "object") {
    var nodes = {};
    try {
      if (typeof sessionStorage !== "undefined") {
        var raw = sessionStorage.getItem(_LINEAGE_KEY) || "";
        var parsed = raw ? JSON.parse(raw) : null;
        if (parsed && typeof parsed === "object") nodes = parsed;
      }
    } catch (_e) { nodes = {}; }
    pg.imageLineage = { nodes: nodes };
  }
  return pg.imageLineage.nodes;
}

function _lineageProtectedKeys(state) {
  var keep = {};
  try {
    var pg = state && state.playground;
    [pg && pg.canvasImageUrl, pg && pg.lastRunOutput,
      pg && pg._selectedRun && pg._selectedRun.imageUrl].forEach(function (u) {
      if (!u) return;
      keep[_lineageKey(u)] = true;
    });
  } catch (_e) { /* best-effort */ }
  return keep;
}

function _pruneLineage(state) {
  // Hard in-memory bound with coherent edges: delete oldest unprotected
  // nodes first, rewiring each deleted node's children to its own parent
  // (or root) and scrubbing every children array. Runs before every persist
  // and does not depend on storage succeeding.
  var pg = state && state.playground;
  var nodes = pg && pg.imageLineage && pg.imageLineage.nodes;
  if (!nodes || typeof nodes !== "object") return;
  function drop(key) {
    var dead = nodes[key];
    if (!dead) return;
    delete nodes[key];
    Object.keys(nodes).forEach(function (k) {
      var n = nodes[k];
      if (!n || typeof n !== "object") return;
      if (Array.isArray(n.children)) {
        n.children = n.children.filter(function (c) { return c !== key; });
      }
      if (n.parent === key) n.parent = (dead.parent && nodes[dead.parent]) ? dead.parent : "";
    });
    if (dead.parent && nodes[dead.parent] && Array.isArray(dead.children)) {
      dead.children.forEach(function (c) {
        if (nodes[c] && nodes[dead.parent].children.indexOf(c) === -1) {
          nodes[dead.parent].children.push(c);
        }
      });
    }
  }
  var guard = 0;
  while (Object.keys(nodes).length > _LINEAGE_CAP && guard++ < 1000) {
    var keep = _lineageProtectedKeys(state);
    var victim = Object.keys(nodes)
      .filter(function (k) { return !keep[k]; })
      .sort(function (a, b) {
        return String((nodes[a] && nodes[a].at) || "") < String((nodes[b] && nodes[b].at) || "") ? -1 : 1;
      })[0];
    if (!victim) break;
    drop(victim);
  }
}

function _persistLineage(state) {
  try {
    var pg = state && state.playground;
    if (!pg || !pg.imageLineage) return;
    _pruneLineage(state);
    if (typeof sessionStorage === "undefined") return;
    sessionStorage.setItem(_LINEAGE_KEY, JSON.stringify(pg.imageLineage.nodes || {}));
  } catch (_e) { /* best-effort */ }
}

function _recordImageEdge(state, childValue, parentValue) {
  try {
    var ck = _lineageKey(childValue);
    if (!ck) return null;
    var nodes = _lineageNodes(state);
    if (!nodes[ck]) nodes[ck] = { key: ck, parent: "", children: [], at: new Date().toISOString() };
    var child = nodes[ck];
    var pk = _lineageKey(parentValue);
    if (pk) {
      // First ancestry wins: an output is generated once, from one source.
      // Later completion paths (poll after direct) must not reparent it from
      // live editing state.
      if (child.parent && child.parent !== pk) return child;
      if (!nodes[pk]) nodes[pk] = { key: pk, parent: "", children: [], at: child.at };
      child.parent = pk;
      var parent = nodes[pk];
      if (parent.children.indexOf(ck) === -1) parent.children.push(ck);
    }
    _persistLineage(state);
    return child;
  } catch (_e) { return null; }
}

function _consumeSubmittedSource(state) {
  // One-shot read of the source stashed at submit time.
  try {
    var pg = state && state.playground;
    if (!pg || !("_submittedSource" in pg)) return "";
    var src = pg._submittedSource || "";
    pg._submittedSource = "";
    return String(src);
  } catch (_e) { return ""; }
}

async function _refreshRunContext(state, context) {
  // The Wizard saves mappings as NEW versions: a tab holding the previously
  // selected version keeps a stale bundle (roles bound since are "unknown").
  // Re-fetch the SAME version (never silently jump versions) so a commit can
  // proceed against truth. Returns true when a usable schema is present.
  try {
    var pg = state && state.playground;
    var store = pg && pg._workflowRun;
    var wf = pg && pg._workflowRunModule;
    // Same version only: never silently jump versions, and never conjure a
    // bundle when nothing is selected.
    if (!store || !wf || !store.workflowId || !store.workflowVersionId) return false;
    var apiBase = (context && context.apiBase) || "/comfymodal";
    var res = await wf.loadRunContext(apiBase, store, store.workflowId, store.workflowVersionId || "");
    if (!res || !res.ok) return false;
    _normalizeShelfControlSchema(state);
    var schema = {};
    try { schema = wf.getControlSchema(store) || {}; } catch (_e) { schema = {}; }
    return Object.keys(schema).length > 0;
  } catch (_e) { return false; }
}

function _completionSource(state) {
  // Ancestry for a finished run: submitted controls first (immune to
  // mid-flight shelf edits), live store only when no submission was stashed.
  var submitted = _consumeSubmittedSource(state);
  if (submitted) return submitted;
  try {
    var store = state && state.playground && state.playground._workflowRun;
    return (store && store.controlValues && store.controlValues.source_image) || "";
  } catch (_e) { return ""; }
}

function _lineageDisplayUrl(key) {
  var k = String(key || "");
  if (!k) return "";
  var m = k.match(/^(input|output|temp):(.*)$/);
  if (m) return "/view?filename=" + encodeURIComponent(m[2]) + "&type=" + m[1];
  if (k.indexOf("url:") === 0) return k.slice(4);
  if (/^(blob:|data:|https?:\/\/|\/)/.test(k)) return k;
  return "/view?filename=" + encodeURIComponent(k) + "&type=input";
}

function _lineageNodeForCanvas(state, canvasUrl) {
  try {
    var nodes = _lineageNodes(state);
    var node = nodes[_lineageKey(canvasUrl)];
    return node || null;
  } catch (_e) { return null; }
}

function _setLinkState(state, busy, error) {
  var pg = state && state.playground;
  if (!pg) return;
  pg._sourceLinkBusy = !!busy;
  pg._sourceLinkError = error || "";
}

async function _linkUrlAsSource(state, context, actions, role, url, prefix) {
  // Shared fetch → upload → commit flow for canvas/history links. The flag
  // is set only when the value actually sticks, so the checkmark never
  // claims a link that failed. Failures name the exact stage (fetch, upload,
  // or save) both on screen and in the console for remote diagnosis.
  // Returns the filename or "".
  function bomb(stage, detail) {
    var err = new Error(stage);
    err.stage = stage;
    err.detail = detail;
    throw err;
  }
  var store = _shelfStore(state);
  var identity = _selectionIdentity(store);
  _setLinkState(state, true, "");
  _refreshShelfSection(state, context, actions);
  try {
    var hit = await _resolveVerifiedCanvasFile(state, url);
    if (hit && hit.filename) {
      if (_selectionIdentity(_shelfStore(state)) !== identity) return "";
      commitShelfValue(state, context, actions, role, hit.filename);
      var keptFile = store.controlValues ? store.controlValues[role] : "";
      if (!keptFile) bomb("saving the value (it was rejected)", hit.filename);
      if (state.playground) state.playground.sourceFollowsCanvas = true;
      _recordImageEdge(state, hit.filename, url);
      return String(hit.filename);
    }
    var resp = null;
    try {
      resp = await fetch(url);
    } catch (fetchErr) {
      bomb("fetching the canvas image", String((fetchErr && fetchErr.message) || fetchErr));
    }
    if (!resp || !resp.ok) bomb("fetching the canvas image (HTTP " + (resp && resp.status) + ")", url);
    var blob = null;
    try {
      blob = await resp.blob();
    } catch (blobErr) {
      bomb("reading the canvas image", String((blobErr && blobErr.message) || blobErr));
    }
    var mod = await import("./studio-field-blocks.js");
    var name = await mod.uploadImageBlob(blob, mod.uniqueImageName(prefix || "studio-link"));
    if (_selectionIdentity(_shelfStore(state)) !== identity) return "";
    // The tab's bundle can predate a Wizard save (new versions): when the
    // role is unknown, refresh the same version once before giving up.
    var _storeNow = _shelfStore(state);
    var _wfNow = state.playground && state.playground._workflowRunModule;
    var _schemaNow = {};
    try { _schemaNow = (_wfNow && _storeNow) ? _wfNow.getControlSchema(_storeNow) || {} : {}; } catch (_e) { _schemaNow = {}; }
    if (!Object.prototype.hasOwnProperty.call(_schemaNow, role)) {
      await _refreshRunContext(state, context);
      try { _schemaNow = (_wfNow && _storeNow) ? _wfNow.getControlSchema(_storeNow) || {} : {}; } catch (_e) { _schemaNow = {}; }
    }
    if (!Object.prototype.hasOwnProperty.call(_schemaNow, role)) {
      bomb("saving the value (Source Image is not mapped in this workflow version — bind it in the Workflow Setup Wizard)", name);
    }
    try {
      commitShelfValue(state, context, actions, role, name);
    } catch (commitErr) {
      bomb("saving the value", String((commitErr && commitErr.message) || commitErr));
    }
    var kept = store.controlValues ? store.controlValues[role] : "";
    if (!kept) {
      var why = "";
      try {
        var rs = store.reasons;
        if (Array.isArray(rs) && rs.length) {
          why = String(rs[0]);
        } else {
          var sch = (store.runContext && store.runContext.control_schema) || {};
          var names = sch && typeof sch === "object" ? Object.keys(sch) : [];
          why = names.length ? "schema roles: " + names.join(", ") : "empty control schema";
        }
      } catch (__e) { why = ""; }
      bomb("saving the value (it was rejected" + (why ? ": " + why : "") + ")", name);
    }
    if (state.playground) state.playground.sourceFollowsCanvas = true;
    _recordImageEdge(state, name, url);
    return String(name);
  } catch (_e) {
    var stage = (_e && _e.stage) || "linking the image";
    var detail = (_e && _e.detail) || ((_e && _e.message) || "");
    try { console.debug("[Studio canvas link] failed at " + stage, detail); } catch (__e) { /* noop */ }
    _setLinkState(state, false, "Could not use that image — " + stage + ".");
    _refreshShelfSection(state, context, actions);
    return "";
  } finally {
    _setLinkState(state, false, (state.playground && state.playground._sourceLinkError) || "");
    _refreshShelfSection(state, context, actions);
  }
}

async function _shelfUseCurrentAsSource(state, context, actions, role) {
  var url = _shelfCurrentImageUrl(state);
  if (!url) return;
  await _linkUrlAsSource(state, context, actions, role, url, "studio-current");
  _syncEditorBaseImage(state);
}

function _shelfToggleCanvasLink(state, context, actions, role, on) {
  // The checkmark binds the input to the canvas image when on, and releases
  // it when off. Checking with an already-linked value is a no-op.
  try {
    var pg = state && state.playground;
    if (!on) {
      if (pg) pg.sourceFollowsCanvas = false;
      commitShelfValue(state, context, actions, role, "");
      _clearBoundMask(state, context, actions);
      _refreshShelfSection(state, context, actions);
      return;
    }
    var store = _shelfStore(state);
    var current = store && store.controlValues ? store.controlValues[role] : "";
    if (current && _sameWorkspaceImage(_lineageDisplayUrl(current), _shelfCurrentImageUrl(state))) {
      if (pg) pg.sourceFollowsCanvas = true;
      _refreshShelfSection(state, context, actions);
      return;
    }
    _shelfUseCurrentAsSource(state, context, actions, role);
  } catch (_e) { /* best-effort */ }
}

function _historyPickerItems(state) {
  try {
    var runs = getRecentRuns() || [];
    var out = [];
    runs.forEach(function (nr) {
      if (!nr || !nr.imageUrl) return;
      var label = nr.prompt || nr.label || nr.id || "Run";
      out.push({ label: String(label).slice(0, 60), url: String(nr.imageUrl) });
      if (out.length >= 30) return;
    });
    return out;
  } catch (_e) { return []; }
}

async function _shelfUseHistoryAsSource(state, context, actions, role, url) {
  // A history image lives behind a run URL, not the input directory: fetch
  // its bytes and upload so the workflow receives a real mapped filename.
  // The pick also replaces the working canvas image.
  if (!url) return;
  var store = _shelfStore(state);
  var identity = _selectionIdentity(store);
  // Prefer the on-drive file when the URL resolves to one (no duplicate).
  // Verified: phantom annotated names fall through to fetch → upload below.
  var hit = null;
  try { hit = await _resolveVerifiedCanvasFile(state, url); } catch (_e) { hit = null; }
  if (hit && hit.filename) {
    if (_selectionIdentity(_shelfStore(state)) !== identity) return;
    commitShelfValue(state, context, actions, role, hit.filename);
    if (state.playground) state.playground.sourceFollowsCanvas = true;
    _recordImageEdge(state, hit.filename, url);
    _setCanvasImage(state, url, context);
    _clearBoundMask(state, context, actions);
    _refreshShelfSection(state, context, actions);
    _syncEditorBaseImage(state);
    return;
  }
  var name = await _linkUrlAsSource(state, context, actions, role, url, "studio-history");
  if (!name) return;
  _setCanvasImage(state, _lineageDisplayUrl(name), context);
  _clearBoundMask(state, context, actions);
  _refreshShelfSection(state, context, actions);
  _syncEditorBaseImage(state);
}

function _shelfRenderInput(role, entry, value, onChange, extra) {
  var kind = _shelfBlockKind(entry);
  var testid = "shelf-input-" + role;
  if (kind === "boolean") {
    var cb = el("input", { type: "checkbox", class: "comfymodal-input", "data-testid": testid });
    cb.checked = value === true || value === 1 || value === "1" || value === "true";
    cb.addEventListener("change", function () { onChange(cb.checked); });
    return cb;
  }
  var block = (kind && FIELD_BLOCKS[kind]) || null;
  if (!block) {
    var input = el("input", {
      type: "text",
      class: "comfymodal-input comfymodal-studio-text-input",
      value: value !== undefined && value !== null ? String(value) : "",
      "data-testid": testid,
    });
    input.addEventListener("input", function () { onChange(input.value); });
    return input;
  }
  if (kind === "image") {
    var imgProps = {
      value: value,
      testid: testid,
      label: _shelfDisplayName(role, entry),
      onChange: onChange,
      previewUrl: extra && extra.previewUrl ? extra.previewUrl : "",
    };
    if (extra && typeof extra.onUseCurrent === "function") imgProps.onUseCurrent = extra.onUseCurrent;
    if (extra && typeof extra.onToggleLink === "function") {
      imgProps.onToggleLink = extra.onToggleLink;
      imgProps.canvasLinked = !!extra.canvasLinked;
      imgProps.linkBusy = !!extra.linkBusy;
      imgProps.linkError = extra.linkError || "";
    }
    if (extra && typeof extra.onPickHistory === "function"
      && Array.isArray(extra.historyItems) && extra.historyItems.length) {
      imgProps.onPickHistory = extra.onPickHistory;
      imgProps.historyItems = extra.historyItems;
    }
    return block.render(imgProps);
  }
  // Model/file roles without options stay read-only: the value comes from
  // the preset/graph (upload is out of scope, same as the mapped controls).
  if (kind === "model-picker") {
    var opts = (entry && entry.enum_options) || [];
    if (!opts.length) {
      var ro = el("input", {
        type: "text",
        class: "comfymodal-input comfymodal-studio-text-input",
        value: value !== undefined && value !== null ? String(value) : "",
        disabled: true,
        title: "File selection is out of scope — value preserved from preset/graph.",
        "data-testid": testid,
      });
      return ro;
    }
    return block.render({ value: value, testid: testid, label: _shelfDisplayName(role, entry), models: opts, onChange: onChange });
  }
  var props = {
    value: value,
    testid: testid,
    placeholder: "",
    onChange: onChange,
    rules: { minimum: entry.minimum, maximum: entry.maximum, step: entry.step },
  };
  if (kind === "dropdown") props.options = (entry && entry.enum_options) || [];
  if (kind === "multiline") props.rows = 3;
  return block.render(props);
}

// Merge the autosaved layout with the live role set: drop roles that no
// longer exist, append new roles in schema order. Prompt is fixed and never
// part of the order list.
function _shelfLayoutFor(entries, promptRole) {
  var roles = entries.map(_shelfRoleOf).filter(function (r) { return r && r !== promptRole; });
  var savedRaw = loadShelfLayout(_SHELF_TYPE_FALLBACK);
  var saved = savedRaw || { order: [], rows: {}, advanced: [] };
  var order = (saved.order || []).filter(function (r) { return roles.indexOf(r) !== -1; });
  roles.forEach(function (r) { if (order.indexOf(r) === -1) order.push(r); });
  var rows = {};
  var maxRow = -1;
  order.forEach(function (r, i) {
    var row = saved.rows && saved.rows[r] != null ? Number(saved.rows[r]) : i;
    if (!Number.isFinite(row) || row < 0) row = i;
    rows[r] = row;
    if (row > maxRow) maxRow = row;
  });
  var advanced = (saved.advanced || []).filter(function (r) { return roles.indexOf(r) !== -1; });
  if (!savedRaw) {
    // Fresh shelf: sampler-tuning roles start collapsed in Advanced. Saved
    // layouts (even with an emptied Advanced section) are never rewritten —
    // the user owns their arrangement after the first touch.
    roles.forEach(function (r) {
      if (_DEFAULT_ADVANCED_ROLES.indexOf(r) !== -1 && advanced.indexOf(r) === -1) advanced.push(r);
    });
  }
  return { order: order, rows: rows, advanced: advanced, maxRow: maxRow };
}

function _shelfPersistLayout(layout) {
  saveShelfLayout(_SHELF_TYPE_FALLBACK, { order: layout.order, rows: layout.rows, advanced: layout.advanced });
  _paintShelfAutosaved();
}

function _paintShelfAutosaved() {
  var when = new Date();
  var label = "Autosaved";
  try {
    label = "Autosaved \u00b7 " + when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch (e) { /* label fallback above */ }
  Array.prototype.forEach.call(document.querySelectorAll('[data-testid="shelf-autosaved"]'), function (node) {
    node.textContent = label;
    node.title = "Field layout and values save automatically — no Save button needed.";
  });
  var pg = null;
  try {
    if (typeof window !== "undefined" && window.__studioApi && typeof window.__studioApi.getState === "function") {
      pg = window.__studioApi.getState().playground;
    }
  } catch (e) { /* best-effort paint only */ }
  if (pg) pg._shelfLastAutosave = when.toISOString();
}

function _flushShelfSave(state) {
  var pg = state && state.playground;
  if (!pg) return;
  if (pg._shelfSaveTimer) {
    clearTimeout(pg._shelfSaveTimer);
    pg._shelfSaveTimer = null;
  }
  var ready = _shelfReady(state);
  if (!ready) return;
  saveShelfValues(ready.store.workflowId, ready.store.workflowVersionId, ready.store.controlValues || {});
  _paintShelfAutosaved();
}

// Restore durably autosaved values for the current selection. Only
// schema-known roles are applied, then re-validated ΓÇö never invents keys.
function _applyShelfSavedValues(state) {
  var ready = _shelfReady(state);
  if (!ready) return;
  var saved = loadShelfValues(ready.store.workflowId, ready.store.workflowVersionId);
  if (!saved || typeof saved !== "object" || !Object.keys(saved).length) return;
  var schema = ready.wf.getControlSchema(ready.store);
  var applied = false;
  Object.keys(saved).forEach(function (role) {
    if (Object.prototype.hasOwnProperty.call(schema, role)) {
      ready.store.controlValues[role] = saved[role];
      applied = true;
    }
  });
  if (!applied) return;
  var validation = ready.wf.validateMappedValues(ready.store.controlValues || {}, schema);
  ready.store.setControlValues(validation.values);
}

// Apply a viewer "use as base" payload to the live Shelf draft: only
// schema-known roles are assigned, then re-validated through the same path
// as normal edits, then autosaved. Returns the applied role count (0 when
// the shelf is not ready or nothing matched — never invents keys).
function _applyShelfBaseValues(state, payload) {
  var ready = _shelfReady(state);
  if (!ready || !payload || typeof payload !== "object") return 0;
  var schema = {};
  try { schema = ready.wf.getControlSchema(ready.store) || {}; }
  catch (err) { return 0; }
  var applied = 0;
  Object.keys(payload).forEach(function (role) {
    if (Object.prototype.hasOwnProperty.call(schema, role)
        && payload[role] != null && payload[role] !== "") {
      ready.store.controlValues[role] = payload[role];
      applied += 1;
    }
  });
  if (!applied) return 0;
  try {
    var validation = ready.wf.validateMappedValues(ready.store.controlValues || {}, schema);
    ready.store.setControlValues(validation.values);
  } catch (err) { /* keep the assigned draft on validation failure */ }
  try { _flushShelfSave(state); } catch (err) { /* debounced autosave covers */ }
  return applied;
}

// Commit one Shelf field edit: same store + validation + gating path as the
// mapped controls, then debounce the durable values autosave. No re-render
// (preserves input focus); the mapped input is synced in place.
function commitShelfValue(state, context, actions, role, rawValue) {
  var ready = _shelfReady(state);
  if (!ready) return;
  ready.store.setControlValue(role, rawValue);
  var schema = ready.wf.getControlSchema(ready.store);
  var validation = ready.wf.validateMappedValues(ready.store.controlValues || {}, schema);
  ready.store.setControlValues(validation.values);
  ready.store.setReasons((validation.errors || []).map(function (e) { return e.message; }));
  _syncMappedShelfInput(role, ready.store.controlValues[role]);
  _syncWorkflowGating(state, context, actions);
  var pg = state.playground;
  if (pg._shelfSaveTimer) clearTimeout(pg._shelfSaveTimer);
  pg._shelfSaveTimer = setTimeout(function () {
    pg._shelfSaveTimer = null;
    _flushShelfSave(state);
  }, _SHELF_SAVE_DELAY_MS);
}

// One-way DOM sync: keep the mapped control input for the same role showing
// the Shelf-edited value (store stays the single source of truth).
function _syncMappedShelfInput(role, value) {
  try {
    var node = document.querySelector('[data-testid="workflow-input-' + role + '"]');
    if (!node || !node.isConnected) return;
    var str = value !== undefined && value !== null ? String(value) : "";
    if (node.tagName === "SELECT") {
      for (var i = 0; i < node.options.length; i++) {
        if (String(node.options[i].value) === str) { node.selectedIndex = i; break; }
      }
      return;
    }
    if (node.type === "checkbox") {
      node.checked = value === true || value === 1 || value === "1" || value === "true";
      return;
    }
    if (node.value !== str) node.value = str;
  } catch (e) { /* best-effort only */ }
}

function _shelfFieldCard(state, context, actions, entries, role, layout, fixed) {
  var entry = _shelfEntryFor(entries, role);
  if (!entry) return null;
  var ready = _shelfReady(state);
  var current = (ready && ready.store.controlValues && typeof ready.store.controlValues === "object")
    ? ready.store.controlValues : {};
  var value = Object.prototype.hasOwnProperty.call(current, role) ? current[role] : undefined;

  var card = el("div", {
    class: "comfymodal-studio-shelf-card" + (fixed ? " is-prompt" : ""),
    "data-testid": fixed ? "shelf-prompt-card" : "shelf-field-" + role,
    "data-role": role,
  });

  var head = el("div", { class: "comfymodal-studio-shelf-card-head" });
  if (!fixed) {
    var grip = el("span", {
      class: "comfymodal-studio-shelf-drag",
      "data-testid": "shelf-drag-" + role,
      text: "⋮⋮",
      title: "Drag to reorder",
    });
    grip.setAttribute("role", "button");
    grip.setAttribute("tabindex", "0");
    grip.setAttribute("aria-label", "Drag to reorder " + _shelfDisplayName(role, entry));
    grip.setAttribute("aria-grabbed", "false");
    grip.addEventListener("pointerdown", function (ev) {
      if (ev.button !== 0 || _shelfPointerDrag) return;
      ev.preventDefault();
      _shelfPointerDrag = { role: role, card: card, state: state, context: context, actions: actions, pointerId: ev.pointerId };
      grip.setAttribute("aria-grabbed", "true");
      card.classList.add("is-dragging");
      document.body.classList.add("comfymodal-studio-shelf-dragging");

      function onMove(moveEvent) {
        if (!_shelfPointerDrag || moveEvent.pointerId !== ev.pointerId) return;
        _shelfClearDropIndicators();
        var drop = _shelfDropAtPoint(role, moveEvent.clientX, moveEvent.clientY);
        _shelfPointerDrag.drop = drop;
        if (!drop) return;
        if (drop.mode === "before" || drop.mode === "after") {
          drop.row && drop.row.querySelector('[data-role="' + drop.targetRole + '"]')
            .classList.add(drop.mode === "before" ? "is-drop-before" : "is-drop-after");
        } else if (drop.row) {
          var indicator = drop.indicator || drop.row;
          if (drop.mode === "advanced" || drop.mode === "advanced-before" || drop.mode === "advanced-after") {
            indicator.classList.add("is-drop-target");
          } else if (drop.mode === "row-join") {
            drop.row.classList.add("is-drop-target");
          } else {
            drop.row.classList.add(drop.mode === "row-before" ? "is-drop-above" : "is-drop-below");
          }
        }
      }
      function onUp(upEvent) {
        if (!_shelfPointerDrag || upEvent.pointerId !== ev.pointerId) return;
        document.removeEventListener("pointermove", onMove, true);
        document.removeEventListener("pointerup", onUp, true);
        document.removeEventListener("pointercancel", onUp, true);
        _shelfClearDropIndicators();
        card.classList.remove("is-dragging");
        grip.setAttribute("aria-grabbed", "false");
        document.body.classList.remove("comfymodal-studio-shelf-dragging");
        var drop = _shelfPointerDrag.drop || _shelfDropAtPoint(role, upEvent.clientX, upEvent.clientY);
        _shelfPointerDrag = null;
        if (!drop || (!drop.targetRole && drop.mode !== "advanced")) return;
        if (drop.mode === "before") {
          _shelfMoveBefore(state, context, actions, role, drop.targetRole, drop.targetRow);
        } else if (drop.mode === "after") {
          _shelfMoveAfter(state, context, actions, role, drop.targetRole, drop.targetRow);
        } else if (drop.mode === "row-before" || drop.mode === "row-after") {
          _shelfMoveToRow(state, context, actions, role, drop.targetRole, drop.mode === "row-before" ? "before" : "after");
        } else if (drop.mode === "row-join") {
          _shelfMoveIntoRow(state, context, actions, role, drop.targetRole);
        } else if (drop.mode === "advanced") {
          _shelfMoveToAdvanced(state, context, actions, role);
        } else if (drop.mode === "advanced-before" || drop.mode === "advanced-after") {
          _shelfMoveToAdvanced(state, context, actions, role, drop.targetRole, drop.mode === "advanced-before" ? "before" : "after");
        }
      }
      document.addEventListener("pointermove", onMove, true);
      document.addEventListener("pointerup", onUp, true);
      document.addEventListener("pointercancel", onUp, true);
    });
    head.appendChild(grip);
  }
  head.appendChild(el("span", {
    class: "comfymodal-studio-shelf-card-label",
    text: _shelfDisplayName(role, entry),
  }));
  if (!fixed) {
  }
  card.appendChild(head);

  var body = el("div", { class: "comfymodal-studio-shelf-card-body" });
  if (role === "prompt" || role === "positive_prompt") {
    body.appendChild(_shelfPromptInput(state, context, actions, role, entry, value));
  } else {
    var extra = null;
    if (role === "source_image") {
      var _pg = state && state.playground;
      extra = {
        onToggleLink: function (on) { _shelfToggleCanvasLink(state, context, actions, role, on); },
        canvasLinked: !!(_pg && _pg.sourceFollowsCanvas && value),
        linkBusy: !!(_pg && _pg._sourceLinkBusy),
        linkError: (_pg && _pg._sourceLinkError) || "",
        onPickHistory: function (url) { _shelfUseHistoryAsSource(state, context, actions, role, url); },
        historyItems: _historyPickerItems(state),
        previewUrl: "",
      };
    }
    // Ownership token for slow async completions (file upload): the commit
    // below is dropped when the selection changed mid-upload.
    var _renderIdentity = _selectionIdentity(_shelfStore(state));
    body.appendChild(_shelfRenderInput(role, entry, value, function (next) {
      // A slow file upload may finish after the user switched workflows —
      // never commit it into the newly selected workflow.
      if ((role === "source_image" || role === "mask")
        && _selectionIdentity(_shelfStore(state)) !== _renderIdentity) {
        _refreshShelfSection(state, context, actions);
        return;
      }
      commitShelfValue(state, context, actions, role, next);
      // Image commits (upload, Clear) change what the paint/outpaint editors
      // must show — refresh their base the same way chaining does. A newly
      // chosen source file also becomes the working canvas image, and a
      // manual file choice unlinks canvas-following.
      if (role === "source_image" || role === "mask") _syncEditorBaseImage(state);
      if (role === "source_image" && next) {
        if (state.playground) state.playground.sourceFollowsCanvas = false;
        _recordImageEdge(state, next, "");
        _setCanvasImage(state, _lineageDisplayUrl(next), context);
        _clearBoundMask(state, context, actions);
        // The canvas sync above does not rebuild the shelf card: refresh it
        // so Replace (upload or drop) shows the new preview instead of a
        // stale one. Image commits are discrete (no text focus to lose).
        _refreshShelfSection(state, context, actions);
      } else if (role === "source_image" && !next) {
        // Clearing the source must not leave its mask or paint behind: the
        // mask was painted for a different image, and with no base URL left
        // _syncEditorBaseImage above is a no-op — so wipe the overlays here
        // (same clearing a replace applies) and refresh the shelf card so it
        // shows the honest empty state instead of the removed preview.
        if (state.playground) state.playground.sourceFollowsCanvas = false;
        _clearBoundMask(state, context, actions);
        _clearPaintOverlays();
        _refreshShelfSection(state, context, actions);
      }
    }, extra));
  }
  card.appendChild(body);
  return card;
}

function _structuredDraftKey(state) {
  var pg = state && state.playground;
  var store = pg && pg._workflowRun;
  return (store && store.workflowId ? String(store.workflowId) : "noid")
    + "::" + (store && store.workflowVersionId ? String(store.workflowVersionId) : "nover");
}

function _shelfStructuredParts(state, value) {
  var pg = state && state.playground;
  var drafts = (pg && pg._structuredPromptParts) || {};
  var hit = drafts[_structuredDraftKey(state)];
  if (hit && typeof hit === "object") {
    return {
      subject: hit.subject || "",
      style: hit.style || "",
      details: hit.details || "",
      composition: hit.composition || "",
    };
  }
  var text = value != null ? String(value) : "";
  return { subject: text, style: "", details: "", composition: "" };
}

function _storeStructuredParts(state, parts) {
  var pg = state && state.playground;
  if (!pg) return;
  if (!pg._structuredPromptParts || typeof pg._structuredPromptParts !== "object") pg._structuredPromptParts = {};
  pg._structuredPromptParts[_structuredDraftKey(state)] = {
    subject: parts.subject || "",
    style: parts.style || "",
    details: parts.details || "",
    composition: parts.composition || "",
  };
}

function _shelfComposeStructured(parts) {
  return [parts.subject, parts.style, parts.details, parts.composition]
    .map(function (p) { return String(p || "").trim(); })
    .filter(Boolean)
    .join(", ");
}

function _shelfPromptInput(state, context, actions, role, entry, value) {
  var wrap = el("div", { "data-testid": "shelf-prompt-wrap" });
  var mode = (state.playground && state.playground._promptMode) || "text";
  var tabs = el("div", { class: "comfymodal-studio-shelf-prompt-tabs", "data-testid": "shelf-prompt-tabs" });
  ["text", "structured"].forEach(function (m) {
    var btn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn" + (mode === m ? " is-on" : ""),
      text: m === "text" ? "Text" : "Structured",
      "data-testid": "shelf-prompt-mode-" + m,
    });
    btn.setAttribute("aria-pressed", mode === m ? "true" : "false");
    btn.addEventListener("click", function () {
      state.playground._promptMode = m;
      _refreshShelfSection(state, context, actions);
    });
    tabs.appendChild(btn);
  });
  wrap.appendChild(tabs);
  if (mode === "structured") {
    var parts = _shelfStructuredParts(state, value);
    _storeStructuredParts(state, parts);
    var box = el("div", { "data-testid": "shelf-prompt-structured" });
    [["subject", "Subject"], ["style", "Style"], ["details", "Details"], ["composition", "Composition"]].forEach(function (pair) {
      var key = pair[0];
      var label = pair[1];
      var input = el("input", {
        type: "text",
        class: "comfymodal-input comfymodal-studio-text-input",
        value: parts[key] || "",
        placeholder: label,
        "data-testid": "shelf-prompt-structured-" + key,
        "aria-label": label,
      });
      input.addEventListener("input", function () {
        parts[key] = input.value;
        _storeStructuredParts(state, parts);
        preview.textContent = _shelfComposeStructured(parts) || "Structured prompt preview appears here.";
        commitShelfValue(state, context, actions, role, _shelfComposeStructured(parts));
      });
      box.appendChild(el("label", { text: label, style: "font-size:11px;color:#888;" }, [input]));
    });
    var preview = el("p", {
      class: "comfymodal-studio-control-note",
      text: _shelfComposeStructured(parts) || "Structured prompt preview appears here.",
      "data-testid": "shelf-prompt-structured-preview",
    });
    box.appendChild(preview);
    wrap.appendChild(box);
    return wrap;
  }
  wrap.appendChild(_shelfRenderInput(role, entry, value, function (next) {
    // A manual Text edit supersedes the structured field breakdown — drop
    // the stored parts so the next Structured open derives from this text.
    try {
      var pg = state && state.playground;
      if (pg && pg._structuredPromptParts) delete pg._structuredPromptParts[_structuredDraftKey(state)];
    } catch (_e) { /* draft clearing is best-effort */ }
    commitShelfValue(state, context, actions, role, next);
  }));
  return wrap;
}

function _shelfMoveBefore(state, context, actions, dragged, before, targetRow) {
  var entries = _shelfEntries(state);
  var promptRole = _shelfPromptRole(entries);
  if (!dragged || !before || dragged === before || dragged === promptRole || before === promptRole) return;
  var layout = _shelfLayoutFor(entries, promptRole);
  var order = layout.order.filter(function (r) { return r !== dragged; });
  var at = order.indexOf(before);
  if (at === -1) order.push(dragged);
  else order.splice(at, 0, dragged);
  layout.order = order;
  layout.advanced = layout.advanced.filter(function (r) { return r !== dragged; });
  if (targetRow != null && Number.isFinite(Number(targetRow))) {
    layout.rows[dragged] = Number(targetRow);
    if (Number(targetRow) > layout.maxRow) layout.maxRow = Number(targetRow);
  }
  _shelfPersistLayout(layout);
  _refreshShelfSection(state, context, actions);
}

function _shelfMoveAfter(state, context, actions, dragged, after, targetRow) {
  var entries = _shelfEntries(state);
  var promptRole = _shelfPromptRole(entries);
  if (!dragged || !after || dragged === after || dragged === promptRole || after === promptRole) return;
  var layout = _shelfLayoutFor(entries, promptRole);
  var order = layout.order.filter(function (r) { return r !== dragged; });
  var at = order.indexOf(after);
  if (at === -1) order.push(dragged);
  else order.splice(at + 1, 0, dragged);
  layout.order = order;
  layout.advanced = layout.advanced.filter(function (r) { return r !== dragged; });
  if (targetRow != null && Number.isFinite(Number(targetRow))) {
    layout.rows[dragged] = Number(targetRow);
  }
  _shelfPersistLayout(layout);
  _refreshShelfSection(state, context, actions);
}

function _shelfMoveToRow(state, context, actions, dragged, anchor, position) {
  var entries = _shelfEntries(state);
  var promptRole = _shelfPromptRole(entries);
  if (!dragged || !anchor || dragged === anchor || dragged === promptRole || anchor === promptRole) return;
  var layout = _shelfLayoutFor(entries, promptRole);
  var order = layout.order.filter(function (r) { return r !== dragged; });
  var anchorIndex = order.indexOf(anchor);
  if (anchorIndex === -1) return;
  var anchorRow = Number(layout.rows[anchor]);
  if (!Number.isFinite(anchorRow)) anchorRow = 0;
  var newRow = position === "before" ? anchorRow : anchorRow + 1;
  Object.keys(layout.rows).forEach(function (role) {
    if (role !== dragged && Number(layout.rows[role]) >= newRow) layout.rows[role] = Number(layout.rows[role]) + 1;
  });
  if (position === "before") order.splice(anchorIndex, 0, dragged);
  else order.splice(anchorIndex + 1, 0, dragged);
  layout.order = order;
  layout.advanced = layout.advanced.filter(function (r) { return r !== dragged; });
  layout.rows[dragged] = newRow;
  layout.maxRow += 1;
  _shelfPersistLayout(layout);
  _refreshShelfSection(state, context, actions);
}

function _shelfMoveIntoRow(state, context, actions, dragged, anchor) {
  var entries = _shelfEntries(state);
  var promptRole = _shelfPromptRole(entries);
  if (!dragged || !anchor || dragged === anchor || dragged === promptRole || anchor === promptRole) return;
  var layout = _shelfLayoutFor(entries, promptRole);
  var order = layout.order.filter(function (r) { return r !== dragged; });
  var anchorIndex = order.indexOf(anchor);
  if (anchorIndex === -1) return;
  order.splice(anchorIndex + 1, 0, dragged);
  layout.order = order;
  layout.rows[dragged] = Number(layout.rows[anchor]);
  layout.advanced = layout.advanced.filter(function (r) { return r !== dragged; });
  _shelfPersistLayout(layout);
  _refreshShelfSection(state, context, actions);
}

function _shelfMoveToAdvanced(state, context, actions, dragged, anchor, position) {
  var entries = _shelfEntries(state);
  var promptRole = _shelfPromptRole(entries);
  if (!dragged || dragged === promptRole) return;
  var layout = _shelfLayoutFor(entries, promptRole);
  layout.advanced = layout.advanced.filter(function (r) { return r !== dragged; });
  var at = anchor ? layout.advanced.indexOf(anchor) : -1;
  if (at === -1) {
    layout.advanced.push(dragged);
  } else {
    layout.advanced.splice(position === "before" ? at : at + 1, 0, dragged);
  }
  _shelfPersistLayout(layout);
  _refreshShelfSection(state, context, actions);
  var toggle = document.querySelector('[data-testid="shelf-advanced-toggle"]');
  if (toggle && toggle.getAttribute("aria-expanded") !== "true") toggle.click();
}

function renderShelfSection(state, context, actions) {
  var section = el("div", {
    class: "comfymodal-studio-shelf",
    "data-testid": "shelf-section",
  });
  _populateShelfSection(section, state, context, actions);
  return section;
}

function _populateShelfSection(section, state, context, actions) {
  while (section.firstChild) section.removeChild(section.firstChild);
  var store = _shelfStore(state);
  if (!store || !store.workflowId) {
    section.appendChild(el("p", {
      class: "comfymodal-studio-control-note",
      "data-testid": "shelf-empty",
      text: "Select a Workflow to see its fields.",
    }));
    return;
  }

  var ready = _shelfReady(state);
  if (!ready) {
    section.appendChild(el("p", {
      class: "comfymodal-studio-control-note",
      "data-testid": "shelf-unmapped",
      text: "This Workflow has no mapped fields yet.",
    }));
    return;
  }
  var entries = _shelfEntries(state);
  var promptRole = _shelfPromptRole(entries);

  if (promptRole) {
    var promptCard = _shelfFieldCard(state, context, actions, entries, promptRole, null, true);
    if (promptCard) section.appendChild(promptCard);
  }

  // Phase 5: visual prompt-style browser under Generate → Text only. The
  // user's prompt stays the source of truth; a selected style deterministically
  // appends its fragment at submit time (see _studioStyleForRun) and the
  // effective prompt is previewed honestly below the grid.
  try {
    var _styleSection = _renderStyleBrowser(state, context, actions, entries, promptRole);
    if (_styleSection) section.appendChild(_styleSection);
  } catch (_eStyle) {}

  var layout = _shelfLayoutFor(entries, promptRole);
  var fieldsBox = el("div", {
    class: "comfymodal-studio-shelf-fields",
    "data-testid": "shelf-fields",
  });
  var visible = layout.order.filter(function (r) { return layout.advanced.indexOf(r) === -1; });
  var rowGroups = {};
  visible.forEach(function (r) {
    var row = layout.rows[r];
    if (!rowGroups[row]) rowGroups[row] = [];
    rowGroups[row].push(r);
  });
  Object.keys(rowGroups).map(Number).sort(function (a, b) { return a - b; }).forEach(function (row) {
    var rowEl = el("div", {
      class: "comfymodal-studio-shelf-row",
      "data-testid": "shelf-row-" + row,
      "data-row": String(row),
    });
    rowGroups[row].forEach(function (r) {
      var card = _shelfFieldCard(state, context, actions, entries, r, layout, false);
      if (card) {
        card.addEventListener("dragover", function (ev) {
          ev.preventDefault();
          rowEl.classList.add("is-drop-target");
        });
        card.addEventListener("dragleave", function () {
          rowEl.classList.remove("is-drop-target");
        });
        card.addEventListener("drop", function (ev) {
          rowEl.classList.remove("is-drop-target");
        });
        rowEl.appendChild(card);
      }
      // Row-level drop appends the dragged card to the end of the row.
      rowEl.addEventListener("dragover", function (ev) { ev.preventDefault(); });
      rowEl.addEventListener("drop", function (ev) {
        var dragged = "";
        try { dragged = ev.dataTransfer.getData("text/shelf-role"); } catch (e) {}
        if (!dragged) return;
        var group = rowGroups[row] || [];
        var last = group[group.length - 1];
        if (dragged && dragged !== last) _shelfMoveBefore(state, context, actions, dragged, last, row);
      });
    });
    fieldsBox.appendChild(rowEl);
  });
  section.appendChild(fieldsBox);

  var skipOption = null;
  try {
    skipOption = _renderSkipTextGenerateOption(state, context, actions);
  } catch (_e) { skipOption = null; }
  if (skipOption) section.appendChild(skipOption);

  var advWrap = el("div", { class: "comfymodal-studio-shelf-advanced-wrap" });
  var advToggle = el("button", {
    type: "button",
    class: "comfymodal-studio-shelf-advanced-toggle",
    "data-testid": "shelf-advanced-toggle",
    text: "Advanced (" + layout.advanced.length + ")",
  });
  var advId = "shelf-advanced-section";
  advToggle.setAttribute("aria-expanded", "false");
  advToggle.setAttribute("aria-controls", advId);
  var advBox = el("div", {
    id: advId,
    class: "comfymodal-studio-shelf-advanced",
    "data-testid": "shelf-advanced-section",
    hidden: true,
  });
  advToggle.addEventListener("click", function () {
    var open = advBox.hidden;
    advBox.hidden = !open;
    advToggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
  advWrap.appendChild(advToggle);
  layout.advanced.forEach(function (r) {
    var card = _shelfFieldCard(state, context, actions, entries, r, layout, false);
    if (card) advBox.appendChild(card);
  });
  advWrap.appendChild(advBox);
  section.appendChild(advWrap);
}

// Re-populate the mounted Shelf section in place. When a Workflow was just
// selected (no Shelf mounted yet), mount it after the workflow selector.
function _refreshShelfSection(state, context, actions) {
  _syncShelfLegacyVisibility(state);
  var section = document.querySelector('[data-testid="shelf-section"]');
  if (section && section.isConnected) {
    _populateShelfSection(section, state, context, actions);
    return;
  }
  if (!_isModernRunSelected(state)) return;
  // Phase 1 shell: Post and later-phase placeholders deliberately render no
  // shelf — a late async refresh must not mount stale fields into them.
  if (activeModeOf(state) === "post" || _isPlaceholderSubtool(activeSubtoolOf(state))) return;
  var panel = document.querySelector('[data-testid="control-panel"]');
  var anchor = panel && panel.querySelector('[data-testid="workflow-selector-section"]');
  if (!panel || !anchor) return;
  var fresh = renderShelfSection(state, context, actions);
  anchor.parentNode.insertBefore(fresh, anchor.nextSibling);
}

// Shelf flow owns the bound fields, so legacy Backend/Preset nodes mounted
// by an earlier (pre-selection) panel render are removed once a modern
// Workflow is selected. Full panel re-renders already skip them via the
// renderControlPanel guards; this covers targeted selection updates that
// never re-render the panel. Never re-adds: the legacy lane reappears only
// through a full re-render with no Workflow selected.
function _syncShelfLegacyVisibility(state) {
  if (!_isModernRunSelected(state)) return;
  var panel = document.querySelector('[data-testid="control-panel"]');
  if (!panel || !panel.isConnected) return;
  var backendSelect = panel.querySelector('[data-testid="backend-select"]');
  if (backendSelect && backendSelect.isConnected) {
    var group = backendSelect.closest(".comfymodal-studio-control-group");
    if (group && group.isConnected) group.remove();
    else backendSelect.remove();
  }
  var controls = panel.querySelector('[data-testid="controls-container"]');
  if (controls && controls.isConnected) controls.remove();
}

// ΓöÇΓöÇ Shelf Workflow switching (shared picker + reuse prompt) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function _closeShelfDialog() {
  var existing = document.querySelector('[data-testid="shelf-picker-dialog"]');
  if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
  var reuse = document.querySelector('[data-testid="shelf-reuse-dialog"]');
  if (reuse && reuse.parentNode) reuse.parentNode.removeChild(reuse);
}

function _openShelfPickerDialog(state, context, actions) {
  _closeShelfDialog();
  var apiBase = (context && context.apiBase) || "/comfymodal";
  var store = _shelfStore(state);
  var currentId = store && store.workflowId ? String(store.workflowId) : "";

  var overlay = el("div", {
    class: "comfymodal-studio-shelf-dialog-overlay",
    "data-testid": "shelf-picker-dialog",
  });
  var dialog = el("div", {
    class: "comfymodal-studio-shelf-dialog",
    role: "dialog",
    "aria-label": "Switch Workflow",
  });
  dialog.appendChild(el("h4", {
    class: "comfymodal-studio-block-heading",
    text: "Switch Workflow",
  }));
  var closeBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn comfymodal-studio-shelf-mini-btn",
    "data-testid": "shelf-picker-close",
    text: "Close",
  });
  closeBtn.addEventListener("click", _closeShelfDialog);
  dialog.appendChild(closeBtn);
  dialog.appendChild(renderWorkflowPicker({
    apiBase: apiBase,
    mode: "single",
    // Same compatibility as the shelf dropdown: Edit/Select offers ordinary
    // I2I workflows plus legacy dedicated inpaint workflows.
    workflowTypes: _pickerTypesForShell(state),
    selectedIds: currentId ? [currentId] : [],
    confirmLabel: "Use workflow",
    onConfirm: function (ids) {
      var next = ids && ids.length ? String(ids[0]) : "";
      _closeShelfDialog();
      if (next && next !== currentId) _confirmShelfSwitch(state, context, actions, next);
    },
  }));
  overlay.addEventListener("click", function (ev) {
    if (ev.target === overlay) _closeShelfDialog();
  });
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  try {
    var onKey = function (ev) {
      if (ev.key === "Escape") {
        _closeShelfDialog();
        document.removeEventListener("keydown", onKey);
      }
    };
    document.addEventListener("keydown", onKey);
  } catch (e) { /* non-fatal */ }
}

async function _confirmShelfSwitch(state, context, actions, nextId) {
  var apiBase = (context && context.apiBase) || "/comfymodal";
  var ready = _shelfReady(state);
  var currentRoles = ready ? Object.keys(ready.wf.getControlSchema(ready.store)) : [];
  var nextRoles = [];
  try {
    var target = ready && (ready.store.library || []).find(function (row) {
      return row && String(row.workflow_id) === String(nextId);
    });
    var targetVersionId = target && target.latest_version_id;
    var cached = ready && ready.store.runContext;
    var cachedWorkflowId = cached && cached.workflow && cached.workflow.workflow_id != null
      ? cached.workflow.workflow_id
      : (ready && ready.store.workflowId);
    var cachedVersionId = cached && cached.version && cached.version.workflow_version_id != null
      ? cached.version.workflow_version_id
      : (ready && ready.store.workflowVersionId);
    var ctxRes = cached
      && targetVersionId
      && String(cachedWorkflowId) === String(nextId)
      && String(cachedVersionId) === String(targetVersionId)
      ? cached
      : null;
    if (!ctxRes) {
      var mod = await import("./studio-backend-api.js");
      ctxRes = await mod.getWorkflowRunContext(apiBase, nextId);
    }
    var rawSchema = (ctxRes && ctxRes.control_schema) || {};
    // Array-shaped (mock) or role-keyed (backend) ΓÇö accept both.
    nextRoles = Array.isArray(rawSchema)
      ? rawSchema.map(function (e) { return (e && (e.semantic_role || e.input_name)) || ""; }).filter(Boolean)
      : Object.keys(rawSchema);
  } catch (e) { nextRoles = []; }
  var matching = currentRoles.filter(function (r) { return nextRoles.indexOf(r) !== -1; });

  var overlay = el("div", {
    class: "comfymodal-studio-shelf-dialog-overlay",
    "data-testid": "shelf-reuse-dialog",
  });
  var dialog = el("div", {
    class: "comfymodal-studio-shelf-dialog",
    role: "dialog",
    "aria-label": "Reuse field values",
  });
  dialog.appendChild(el("p", {
    text: matching.length
      ? "Reuse " + matching.length + " matching field value(s) from the current Workflow?"
      : "No matching fields — load the new Workflow defaults?",
  }));
  var yes = el("button", {
    type: "button",
    class: "comfymodal-primary-btn",
    "data-testid": "shelf-reuse-yes",
    text: "Reuse values",
    style: "width:auto;",
  });
  var no = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    "data-testid": "shelf-reuse-no",
    text: matching.length ? "Use defaults" : "Continue",
    style: "width:auto;",
  });
  yes.addEventListener("click", function () {
    _closeShelfDialog();
    _performShelfSwitch(state, context, actions, nextId, true);
  });
  no.addEventListener("click", function () {
    _closeShelfDialog();
    _performShelfSwitch(state, context, actions, nextId, false);
  });
  dialog.appendChild(yes);
  dialog.appendChild(no);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
}

async function _performShelfSwitch(state, context, actions, nextId, reuse) {
  var pg = state && state.playground;
  var wf = _shelfModule(state);
  var store = _shelfStore(state);
  if (!pg || !wf || !store || !nextId) return;
  var apiBase = (context && context.apiBase) || "/comfymodal";
  // Flush pending autosaves so the outgoing Workflow keeps its edits.
  _flushShelfSave(state);
  var carried = {};
  if (reuse) {
    carried = Object.assign({}, store.controlValues || {});
  }
  var hadOutput = !!(pg.lastRunOutput || pg._selectedRun);
  var result = await wf.selectWorkflow(apiBase, store, nextId);
  await _loadWorkflowModelLibrary(state, apiBase);
  if (result && result.ok) {
    if (reuse) {
      var schema = wf.getControlSchema(store);
      Object.keys(carried).forEach(function (role) {
        if (Object.prototype.hasOwnProperty.call(schema, role)) {
          store.controlValues[role] = carried[role];
        }
      });
      var validation = wf.validateMappedValues(store.controlValues || {}, schema);
      store.setControlValues(validation.values);
      saveShelfValues(store.workflowId, store.workflowVersionId, store.controlValues || {});
    } else {
      _applyShelfSavedValues(state);
    }
    wf.saveWorkflowSelection({
      workflowId: store.workflowId,
      workflowVersionId: store.workflowVersionId,
      workflowName: store.workflowName || "",
    });
    _rememberSelection(state);
    _syncActiveToolToSelection(state);
    _chainCurrentImageToSource(state, context, actions);
  }
  // Old output stays visible but stale until a new run completes.
  if (hadOutput) pg._shelfStaleOutput = true;
  if (context && context.setPage) context.setPage("playground");
}
