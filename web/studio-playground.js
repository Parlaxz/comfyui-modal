// Modal Studio â€” Playground
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
import { runStudioWorkflow, getStudioRunStatus, stopExperiment, listModels } from "./studio-backend-api.js";
import { loadModalOptions } from "./studio-output-preferences.js";

import { resolveRunImageUrl, hasRunImage, normalizeStudioRun, normalizeGenerationSettings, buildWaterfallLines } from "./studio-run-normalizer.js";
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
} from "./studio-playground-state.js";
import {
  createPlaygroundRunController,
  projectRunToLegacy,
  LEGACY_TERMINAL_STATUSES,
} from "./studio-playground-run.js";
import { updateRunAnnotation, saveRunOutput } from "./studio-backend-api.js";
import { createHistoryRepository } from "./history-v2-repository.js";
import { requestHistoryRecordFocus } from "./studio-history-v2.js";

export async function buildStudioModalOptions(apiBase) {
  const options = await loadModalOptions(apiBase);
  if (typeof window !== "undefined") window._comfyModalExecutionMode = options.execution_mode;
  return options;
}
import { el, createZoomableImageEl, createImagePreviewOverlay, renderEmptyState } from "./studio-ui.js";
import { renderLoadingState } from "./studio-loading.js";
import { BINDABLE_INPUTS } from "./studio-bindable-inputs.js";
import { FIELD_BLOCKS } from "./studio-field-blocks.js";
import { renderWorkflowPicker } from "./studio-workflow-picker.js";
import {
  loadShelfLayout,
  saveShelfLayout,
  loadShelfValues,
  saveShelfValues,
} from "./studio-playground-state.js";

// â”€â”€ Polling helper for experiment status â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
      // Transient fetch error â€” keep current state until deadline
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
      // Terminal reached â€” stop polling (duplicate polls are no-ops anyway).
      if (_ctrl.isTerminal()) _stopPolling(state);
      return;
    }

    _stopPolling(state);
  }, POLL_INTERVAL_MS);
  // Store timer reference on state (survives re-renders) instead of
  // container (destroyed on re-render from context.setPage calls).
  if (state && state.playground) state.playground._pollTimer = pollTimer;
}

// â”€â”€ Effective Controls builder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // A persisted draft contains explicit user edits â€” load into
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
 * Safe to call on every render â€” performs a synchronous localStorage write.
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

// â”€â”€ Recent runs state management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//
// Reusable loader/state-owned collection of recent runs, refreshed:
//   - on initial hydration
//   - after finalized completion
//   - after preset deletion if needed
//   - when returning to Playground after History changes
// Hydration comes from the History V2 feed (same durable authority as the
// History page) â€” legacy feeds are no longer consulted.

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

export async function refreshRecentRuns(apiBase) {
  try {
    const repo = await _getRecentRunsRepo(apiBase);
    const page = await repo.listFeed({ limit: 50, sort: "newest" }); 
    var items = [];
    (page.items || []).forEach(function (rec) {
      if (!rec) return;
      if (rec.kind === "experiment") {
        var coverThumb = "";
        var cover = rec.cover || [];
        for (var ci = 0; ci < cover.length; ci++) {
          var c = cover[ci];
          if (c && (c.thumbUrl || c.previewUrl)) {
            coverThumb = c.thumbUrl || c.previewUrl;
            break;
          }
        }
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
        var imageUrl = feat ? (feat.thumbUrl || feat.previewUrl || "") : "";
        // Keep only finished generations that actually produced an image.
        if (!((rec.status === "completed" || rec.status === "completed_with_failures") && imageUrl)) return;
        items.push({
          kind: "generation",
          id: rec.id,
          experimentId: "",
          runId: rec.runId || rec.id,
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

    // Sort by created time (newest first)
    items.sort(function (a, b) {
      var aTime = a.completedAt || a.startedAt || "";
      var bTime = b.completedAt || b.startedAt || "";
      return bTime.localeCompare(aTime);
    });

    // Deduplicate by ID (first occurrence of each key wins â€” newest)
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

// ── Same-run history timings fallback (Shelf single-run slice) ───────────
//
// When a completed single run carries no direct timings AND the History V2
// feed has no projection for it yet (mocked + raced backends), fall back to
// the legacy history entry for the SAME run id only — matched on the
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

// â”€â”€ Hydration helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//
// Restore saved selection, fetch presets + history, validate preset,
// restore latest completed run preview plus draft/snapshot defaults.

export async function hydratePlayground(state, context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // 1. Load saved selection from localStorage
  const saved = loadSelection();

  // 2. No backend presets exist any more: the selected Workflow (and its
  // current Version) is the only run identity, and the run store hydrates it.
  const featureId = (saved && saved.featureId) || "txt2img";
  if (state.playground) {
    state.playground.featureId = featureId;
    state.playground.selectedBackendId = "";
  }
  const targetPresetId = "";

  const experimentDraft = loadExperimentDraft(targetPresetId, featureId);
  if (state.playground) {
    state.playground.experimentAxes = experimentDraft ? experimentDraft.experimentAxes : {};
    state.playground.compareBackendIds = experimentDraft ? experimentDraft.compareBackendIds : [];
  }

  // 6a. Try to restore from localStorage persisted run result first
  const persistedRun = loadRunResult(targetPresetId, featureId);
  if (persistedRun) {
    state.playground._selectedRun = persistedRun;
    state.playground.lastRunOutput = persistedRun.imageUrl || null;
  } else if (!isCarouselCleared()) {
    await refreshRecentRuns(apiBase);
    if (targetPresetId) {
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
          saveRunResult(targetPresetId, featureId, latest);
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

  // 8. Kick off the modern workflow selector init (idempotent â€” it is also
  // started from renderControlPanel; this covers hydration-only renders).
  try {
    initWorkflowRun(state, context);
  } catch (e) {
    // Never block legacy hydration on the workflow selector.
  }
}

// â”€â”€ Main Playground renderer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function renderPlayground(state, context) {
  const container = el("div", { class: "comfymodal-studio-playground" });

  // Phase I8: accessible page heading. The Playground has no visible title
  // by design, so this is a visually-hidden h2 (clip pattern — never
  // display:none) directly under the shell h1. Card/run labels are NOT
  // promoted to headings.
  container.appendChild(el("h2", {
    text: "Playground",
    "data-testid": "playground-page-title",
    style: "position:absolute;width:1px;height:1px;margin:-1px;padding:0;border:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;",
  }));

  // â”€â”€ Scoped tracker lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // Studio progress is driven by a scoped tracker (per-run), NOT the
  // global shared tracker. This prevents unrelated ComfyUI executions
  // from driving the Studio progress UI.
  //
  // Scoped trackers are created in _modernRunSubmit (single runs) and in the
  // experiment run handlers, then disposed on terminal states.
  // The _scopedTracker reference in state.playground is managed there.
  //
  // Not subscribed for progress UI updates â€” only scoped trackers drive
  // the Studio progress panel to avoid unrelated ComfyUI executions
  // interfering.

  const leftPanel = renderControlPanel(state, context);
  const resizeHandle = _createResizeHandle(leftPanel);
  const rightWorkspace = renderWorkspace(state, context);

  container.appendChild(leftPanel);
  container.appendChild(resizeHandle);
  container.appendChild(rightWorkspace);

  return container;
}

var _PANEL_WIDTH_KEY = "comfymodal-studio-panel-width";
var _PANEL_WIDTH_MIN = 200;
var _PANEL_WIDTH_MAX = 600;
var _PANEL_WIDTH_DEFAULT = 400;

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

// â”€â”€ Left Control Panel (preset-driven) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderControlPanel(state, context) {
  const panel = el("div", { class: "comfymodal-studio-control-panel", "data-testid": "control-panel" });

  const isExperiment = state.playground && state.playground.experimentMode;
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const currentSpec = FEATURE_SPECS.find((f) => f.id === currentFeatureId) || FEATURE_SPECS[0];

  // Actions for state mutations (called by event handlers)
  const actions = buildActions(state, context);
  if (state.playground) state.playground._runActions = actions;
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // Hydrate: restore saved state.
  // Phase 1 (sync): load saved selection from localStorage so the
  // initial render shows the correct backend selection without needing
  // a hydration-triggered re-render that would close an open <select>.
  if (!state.playground._hydrationDone) {
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

  // Experiment toggle (always at top of control panel)
  panel.appendChild(renderExperimentToggle(state, actions));

  // If experiment mode, render experiment-mode controls (context passed explicitly)
  if (isExperiment) {
    const expBlock = renderExperimentMode(state, actions, context);
    panel.appendChild(expBlock);
  }

  // â”€â”€ Workflow Selector (modern workflow-driven runs) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // Empty-state only until a workflow is chosen.
  panel.appendChild(renderWorkflowSelector(state, context, actions));

  // Shelf field cards (Studio Workflow effort, leaf 1.2.2): bound field
  // cards for the selected Workflow. Prompt fixed at top; output stays the
  // right-side result panel (never a movable card).
  if (_isModernRunSelected(state)) {
    panel.appendChild(renderShelfSection(state, context, actions));
  }


  // â”€â”€ Run Button â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  panel.appendChild(renderRunButton(state, context, actions));

  // Reset to defaults link
  const resetLink = el("button", {
    class: "comfymodal-studio-reset-link",
    text: "Reset to defaults",
    style: "background:none;border:none;color:var(--color-accent);cursor:pointer;font-size:var(--font-size-sm);padding:4px 0;text-decoration:underline;",
    onclick: function () {
      if (actions && actions.resetToDefaults) actions.resetToDefaults();
    },
  });
  panel.appendChild(resetLink);

  return panel;
}

// â”€â”€ Actions builder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function buildActions(state, context) {
  return {
    setFeature(featureId) {
      clearTimeout(state.playground._draftSaveTimer);

      // Preserve current run result before switching
      const prevPresetId = state.playground.selectedBackendId;
      const prevFeatureId = state.playground.featureId;
      const prevRun = state.playground._selectedRun;
      if (prevPresetId && prevFeatureId && prevRun) {
        saveRunResult(prevPresetId, prevFeatureId, prevRun);
      }

      state.playground.featureId = featureId;
      // Clear stale controls when feature changes
      state.playground.controls = {};
      state.playground._selectedRun = null;
      state.playground.lastRunOutput = null;
      const presetId = state.playground.selectedBackendId;
      const currentPreset = getCurrentPresetForSelection(state, presetId);

      // Load persisted run result for the new feature
      const loadedRun = loadRunResult(presetId, featureId);
      if (loadedRun) {
        state.playground._selectedRun = loadedRun;
        state.playground.lastRunOutput = loadedRun.imageUrl || null;
      }

      hydrateControlsForSelection(state, presetId, featureId, currentPreset);
      // Clear stale run state so Run button re-enables
      if (state.playground) state.playground.runState = null;
      // Dispose scoped tracker â€” switching features invalidates current run
      _disposeScopedTracker(state);
      // Persist selection
      saveSelection(state.playground.selectedBackendId, featureId);
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
      if (prevPresetId && prevFeatureId && prevRun) {
        saveRunResult(prevPresetId, prevFeatureId, prevRun);
      }

      state.playground.selectedBackendId = backendId;
      // Clear stale controls when preset changes to avoid sending
      // controls that the new preset doesn't support
      state.playground.controls = {};
      state.playground._selectedRun = null;
      state.playground.lastRunOutput = null;
      const currentPreset = getCurrentPresetForSelection(state, backendId);

      // Load persisted run result for the new preset+feature
      const loadedRun = loadRunResult(backendId, state.playground.featureId);
      if (loadedRun) {
        state.playground._selectedRun = loadedRun;
        state.playground.lastRunOutput = loadedRun.imageUrl || null;
      }

      hydrateControlsForSelection(state, backendId, state.playground.featureId, currentPreset);
      // Clear stale run state so Run button re-enables
      if (state.playground) state.playground.runState = null;
      // Dispose scoped tracker â€” switching backends invalidates current run
      _disposeScopedTracker(state);
      // Persist selection
      saveSelection(backendId, state.playground.featureId);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    setControl(ctrlId, value) {
      if (!state.playground.controls) state.playground.controls = {};
      state.playground.controls[ctrlId] = value;
      if (ctrlId === 'prompt' && state.playground.experimentAxes && state.playground.experimentAxes.prompt && state.playground.experimentAxes.prompt.enabled && state.playground.experimentAxes.prompt.values && state.playground.experimentAxes.prompt.values.length > 0) {
        state.playground.experimentAxes.prompt.values[0] = value;
        // Persist experiment draft â€” prompt-axis first value changed
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
      state.playground.experimentMode = enabled;
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
      // Persist experiment draft â€” axes toggles are a persistence trigger
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
      // Persist experiment draft â€” axis values changed
      _saveExperimentDraftFromState(state);
      // Re-render when value count changes (add/remove), but NOT on every
      // keystroke â€” that would thrash the UI during text input.
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
        // Clean up captured running config â€” a new run will re-capture
        if (state.playground) delete state.playground._runningExperimentConfig;
        _disposeScopedTracker(state);
      }

      if (runState && newStatus === "completed" && prevStatus !== "completed") {
        // A new run completed — the Shelf output is fresh again: clear the
        // stale mark set by Workflow switching.
        if (state.playground) state.playground._shelfStaleOutput = false;
        // A new run completed â€” re-enable the carousel synchronously so
        // subsequent re-renders and page loads show recent runs again.
        // Done BEFORE the async refresh so the flag does not persist and
        // suppress the hydrated output on the next render.
        setCarouselCleared(false);

        // Persist primary output URL so canvas shows result
        if (runState.primaryOutput) {
          state.playground.lastRunOutput = runState.primaryOutput;
        }
        // Keep preset/feature selected
        saveSelection(state.playground.selectedBackendId, state.playground.featureId);
        // Refresh recent runs and try to select finalized normalized run
        const apiBase = (context && context.apiBase) || "/comfymodal";
        refreshRecentRuns(apiBase).then(function (runs) {
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
            // Never nullify lastRunOutput â€” primaryOutput has already been set.
            // Only overwrite if the matched run carries a valid imageUrl.
            if (matched.imageUrl) {
              state.playground.lastRunOutput = matched.imageUrl;
            }
            // Persist the finalized run result to localStorage
            saveRunResult(
              state.playground.selectedBackendId,
              state.playground.featureId || "txt2img",
              matched
            );
            if (context && context.setPage) context.setPage("playground");
          }
          if (!matched && experimentId) {
            // V2 has no projection for this run yet — assemble the finalized
            // run from the SAME run's history entry so its canonical timings
            // still reach the timing card (stages → summary → duration).
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
                saveRunResult(
                  state.playground.selectedBackendId,
                  state.playground.featureId || "txt2img",
                  fallback
                );
              } catch (e) {}
              if (context && context.setPage) context.setPage("playground");
            });
          }
          // Note: setCarouselCleared was already called synchronously above
        });
      } else if (!runState) {
        // Clearing runState â€” preserve lastRunOutput and _selectedRun so
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

// â”€â”€ Control Group wrapper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderControlGroup(labelText, inputEl) {
  const group = el("div", { class: "comfymodal-studio-control-group" });
  if (labelText) {
    const label = el("label", { class: "comfymodal-studio-control-label", text: labelText });
    group.appendChild(label);
  }
  if (inputEl) group.appendChild(inputEl);
  return group;
}

// â”€â”€ Backend Selector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//
// Loads runtime presets from the Studio backend abstraction (getRuntimePresets).
// Filters by feature compatibility when appropriate.
// In empty state, links to the Backend tab (H10: no Legacy Setup funnels).

// â”€â”€ Workflow Run Selector (modern workflow-driven runs) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
 * Must never throw — it is awaited inside the Workflow-change handler, and a
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

function _workflowGatingInfo(store, wf, state) {
  if (!store) return { text: "Select a workflow", color: "" };
  if (store.statusLine) return { text: store.statusLine, color: "#d9a441" };
  if (store.status === "error") return { text: store.error || "Load error", color: "#f87171" };
  if (!store.workflowId) return { text: "Select a workflow", color: "" };
  if (!store.workflowVersionId) return { text: "Select a Workflow", color: "" };
  if (store.status === "loading" || !wf || !store.runContext) {
    return { text: store.status === "loading" ? "Loading\u2026" : "Loading workflow\u2026", color: "" };
  }
  const modelRecords = (state && state.playground && state.playground._workflowModelLibrary) || [];
  const { runnable, reasons } = _resolveWorkflowRunnable(store, wf, modelRecords);
  if (runnable) return { text: "Ready to run", color: "var(--color-success)" };
  return { text: reasons.length ? reasons.join("; ") : "Not runnable", color: "#d9a441" };
}

function _workflowSelectEl(state, actions, context) {
  const store = state && state.playground && state.playground._workflowRun;
  const select = el("select", {
    class: "comfymodal-input comfymodal-studio-select",
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
  (store.library || []).forEach((w) => {
    const opt = el("option", { value: String(w.workflow_id), text: _workflowOptionLabel(w) });
    if (store.workflowId && String(store.workflowId) === String(w.workflow_id)) opt.selected = true;
    select.appendChild(opt);
  });
  select.disabled = (store.library || []).length === 0;
  select.addEventListener("change", () => {
    _handleWorkflowChange(state, context, actions, select.value);
  });
  return select;
}

function _workflowGatingLineEl(state, wf, context) {
  const store = state && state.playground && state.playground._workflowRun;
  const info = _workflowGatingInfo(store, wf, state);
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

  container.appendChild(_workflowSelectEl(state, actions, context));
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
  // Shelf: restore durably autosaved values only when the caller opted in
  // (workflow/version switches and persisted-selection restore). Preset
  // switches and handoffs carry explicit values and must not be clobbered.
  // The Shelf cards refresh in every case (prompt fixed top, layout, stale).
  if (opts && opts.applySaved) _applyShelfSavedValues(state);
  _refreshShelfSection(state, context, actions);
  _syncRunButtonGating(state, context, actions);
}

function _syncWorkflowGating(state, context, actions) {
  const line = document.querySelector('[data-testid="workflow-run-gating"]');
  if (line) {
    const store = state && state.playground && state.playground._workflowRun;
    const wf = state && state.playground && state.playground._workflowRunModule;
    const info = _workflowGatingInfo(store, wf, state);
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

// â”€â”€ Workflow run init / selection flows â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

      // The library must be present for resolveHandoffSelection and the
      // saved-selection restore to validate the requested entities.
      await wf.loadWorkflowLibrary(apiBase, store);

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

  const wfRes = await wf.selectWorkflow(apiBase, store, handoff.workflowId);
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
}

async function _restoreWorkflowSelection(state, context, actions, wf, store, saved) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  const workflow = (store.library || []).find((w) => String(w.workflow_id) === String(saved.workflowId));
  if (!workflow) {
    store.statusLine = "Saved workflow is no longer available";
    store.setStatus("idle");
    store.setReasons([]);
    wf.clearWorkflowSelection();
    return;
  }
  const wfRes = await wf.selectWorkflow(apiBase, store, saved.workflowId);
  if (!wfRes.ok) {
    store.statusLine = wfRes.error || "Saved workflow is no longer available";
    wf.clearWorkflowSelection();
    return;
  }
  if (saved.workflowVersionId) {
    // A workflow has one version, so a restored id is a hint, not a choice.
    // Snap to whatever the workflow's latest is now rather than failing when
    // the saved version is gone: the run context is version-agnostic to the
    // user, who has no way to pick a different one any more.
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
    const verRes = await wf.selectVersion(apiBase, store, target.workflow_version_id);
    if (!verRes.ok) {
      store.statusLine = verRes.error || "Requested version no longer available";
      return;
    }
  }
  await _loadWorkflowModelLibrary(state, apiBase);
}

async function _handleWorkflowChange(state, context, actions, workflowId) {
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf || !workflowId) return;
  const apiBase = (context && context.apiBase) || "/comfymodal";
  store.handoffError = null;
  const result = await wf.selectWorkflow(apiBase, store, workflowId);
  await _loadWorkflowModelLibrary(state, apiBase);
  if (result && result.ok) {
    wf.saveWorkflowSelection({
      workflowId: store.workflowId,
      workflowVersionId: store.workflowVersionId,
      workflowName: store.workflowName || "",
    });
  }
  // Shelf: a new Workflow loads its own durably autosaved field values.
  _rerenderWorkflowSection(state, context, actions, { applySaved: true });
}

// â”€â”€ Run button gating (modern mode) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function _applyModernRunButtonState(state, context, actions, btn, reason) {
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf) return;
  // Never clobber an in-flight run's button state.
  const runState = state && state.playground && state.playground.runState;
  if (runState && runState.status && LEGACY_TERMINAL_STATUSES.indexOf(runState.status) === -1) return;
  if (reason) while (reason.firstChild) reason.removeChild(reason.firstChild);
  const g = _workflowGatingInfo(store, wf, state);
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
  const { runnable, reasons } = _resolveWorkflowRunnable(store, wf, modelRecords);
  if (!runnable) {
    btn.disabled = true;
    btn.textContent = "Run";
    btn.title = reasons.length ? reasons.join("; ") : "Not runnable";
    // See above â€” no competing legacy onclick while gated in modern mode.
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
  if (!_isModernRunSelected(state)) return;
  const btn = _resolvePrimaryRunButton();
  if (!btn) return;
  const section = btn.closest(".comfymodal-studio-run-section");
  const reason = section ? section.querySelector(".comfymodal-studio-disabled-reason") : null;
  _applyModernRunButtonState(state, context, actions, btn, reason);
}

// â”€â”€ Modern run submission â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async function _modernRunSubmit(state, context, actions, btn) {
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf) {
    if (btn) { btn.disabled = false; btn.textContent = "Run"; }
    return;
  }
  const apiBase = (context && context.apiBase) || "/comfymodal";
  var ctrl = _getRunController(state, actions);
  if (!ctrl) {
    if (btn) { btn.disabled = false; btn.textContent = "Run"; }
    return;
  }

  // Known incompatible models must never execute, even on a forced click.
  // Gating mirrors the Run-button state; this is a defensive re-check so a
  // terminal-state re-run cannot bypass the disabled button.
  const _modelRecords = (state && state.playground && state.playground._workflowModelLibrary) || [];
  const _gated = _resolveWorkflowRunnable(store, wf, _modelRecords);
  if (!_gated.runnable) {
    const _reasonText = (_gated.reasons && _gated.reasons.length)
      ? _gated.reasons[0]
      : "Workflow is not runnable";
    ctrl.beginRun();
    ctrl.mark("submit_entered");
    ctrl.applyLocalError(_reasonText);
    if (btn) { btn.disabled = false; btn.textContent = "Run"; }
    _syncRunButtonGating(state, context, actions);
    return;
  }

  ctrl.mark("submit_entered");

  // Put determinate sampler fields into running state BEFORE the remote call
  // (mirrors the legacy handler). beginRun must precede any applyLocalError.
  var _modernSteps = store.controlValues && store.controlValues.steps;
  var _runMaxSteps = (_modernSteps != null && Number(_modernSteps) > 0) ? Number(_modernSteps) : 0;
  ctrl.beginRun({ samplerMaximum: _runMaxSteps });

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
      if (btn) { btn.disabled = false; btn.textContent = "Run"; }
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
    if (btn) { btn.disabled = false; btn.textContent = "Run"; }
    return;
  }

  // Clear previous output so canvas shows live progress immediately
  if (state && state.playground) {
    state.playground.lastRunOutput = null;
    state.playground._selectedRun = null;
  }
  if (state && state.playground && state.playground.runState) delete state.playground.runState._localStartTime;
  _startLocalElapsedTimer(state, context);

  const modalOptions = await buildStudioModalOptions(apiBase);

  // Capture client-side timestamps at press time (top-level `trace` for server)
  var t0_perf_ms = performance.now();
  var t0_now = Date.now();

  ctrl.mark("build_start");
  const payload = wf.buildRunPayload(apiBase, store, modalOptions, {
    t0_perf_ms: t0_perf_ms,
    t0_perf_now_ms: t0_now,
    t0_client_press_ms: t0_now,
  });
  ctrl.mark("build_end");

  ctrl.mark("http_invoked");
  const result = await runStudioWorkflow(apiBase, payload);
  ctrl.mark("backend_ack");

  if (result && result.status === "ok") {
    // â”€â”€ Direct run: result is already completed, no polling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if (_handleDirectRunResult(result, state, context, actions, merged.values)) {
      return;
    }
    // â”€â”€ Scheduler path: submission, start polling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    const errMsg = (result && result.message) || "Run failed.";
    if (result && result.error_code) {
      console.error("[Studio run] execution failed", {
        error_code: result.error_code,
        error: result.error || null,
      });
    }
    if (ctrl) ctrl.applyLocalError(errMsg);
    if (btn) { btn.disabled = false; btn.textContent = "Run"; }
  }
}

// â”€â”€ Info Hint helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
  hint.textContent = "\u24d8";  // â“˜ circled info icon

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

// â”€â”€ Render a single control â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Schema-kind dispatch (backend truth) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    // Preserve falsy zero/false â€” only truly missing treated as default
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

  // â”€â”€ Static CONTROL_DEFS type dispatch (fallback) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Steps: Use Recommended (N) button â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

// â”€â”€ Run Button â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// â”€â”€ Single-run submit helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//
// Immediately submits a single run using visible controls.
// Deduplicated from the inline handler in renderRunButton so that
// completed/error state can re-submit in a single click.

function _disposeScopedTracker(state) {
  // Note: does NOT clean _localElapsedTimer â€” the local timer is owned by
  // _startLocalElapsedTimer which handles cleanup and re-creation across
  // new-run boundaries. Terminal cleanup is done by setRunState.

  var st = state.playground && state.playground._scopedTracker;
  if (st && typeof st.dispose === "function") {
    try { st.dispose(); } catch {}
  }
  if (state.playground) state.playground._scopedTracker = null;
}

// â”€â”€ Canonical run controller (single lifecycle authority) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    // DOM-targeted elapsed update â€” avoids full page teardown on every tick
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
 * Handle a direct-run completed result â€” no polling or journal needed.
 * Returns true when the result was a direct_run and was handled,
 * false when the caller should fall through to the scheduler/polling path.
 */
function _handleDirectRunResult(result, state, context, actions, controls) {
  if (!result || !result.direct_run) return false;
  if (result.status !== "ok") return false;

  const apiBase = (context && context.apiBase) || "/comfymodal";
  const outputPaths = result.output_paths || [];
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
  const timings = result.timings || {};
  var rawRun = {
    id: result.runId || result.runHistoryId || meta.experiment_id || "",
    experiment_id: result.experimentId || meta.experiment_id || "",
    status: "completed",
    output_path: result.output_path || (outputPaths.length > 0 ? outputPaths[0] : ""),
    primary_asset_id: primaryAssetId,
    started_at: null,
    completed_at: result.completed_at || null,
    duration_ms: null,
    workflow_hash: meta.workflow_hash || "",
    extra: {
      experiment_id: result.experimentId || meta.experiment_id || "",
      studio_preset_id: meta.studio_preset_id || "",
      studio_preset_label: meta.preset_label || "",
      studio_snapshot_id: meta.studio_snapshot_id || "",
      studio_feature_id: meta.studio_feature_id || "",
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
      state.playground._selectedRun = normalized;
    }
    // Persist via saveRunResult so the result survives reload.
    var _presetId = meta.studio_preset_id || "";
    var _featureId = meta.studio_feature_id || "";
    if (_presetId && _featureId) {
      saveRunResult(_presetId, _featureId, normalized);
    }
  }

  var ctrl = _getRunController(state, actions);
  if (ctrl) {
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
  if (container.isConnected) {
    while (reason.firstChild) reason.removeChild(reason.firstChild);
    _applyModernRunButtonState(state, context, actions, btn, reason);
  }

  return container;
}

// â”€â”€ Progress Section â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//
// Displays shared progress state: overall bar, current stage/node, sampler
// step progress, completed/total nodes, elapsed time, queue/startup state,
// clear failure state, and completed duration.

function renderProgressSection(state, context) {
  const section = el("div", {
    class: "comfymodal-studio-metadata-section",
    "data-testid": "progress-section",
    style: "display:none;",
  });

  const runState = state.playground && state.playground.runState;
  if (!runState || LEGACY_TERMINAL_STATUSES.indexOf(runState.status) !== -1) {
    // Terminal (or no run yet): retain the final stage label so the
    // section evidences completion instead of going blank. Completed and
    // error detail continues to render in the metadata section.
    if (runState) {
      var terminalLabel = "Completed";
      if (runState.status === "error") terminalLabel = "Error";
      else if (runState.status === "canceled") terminalLabel = "Canceled";
      else if (runState.status === "interrupted") terminalLabel = "Interrupted";
      section.style.display = "block";
      section.appendChild(el("span", {
        "data-testid": "progress-stage",
        style: "font-size:10px;color:#aaa;",
        text: "Stage: " + terminalLabel,
      }));
    }
    return section;
  }

  section.style.display = "block";

  // Overall progress bar
  const barContainer = el("div", {
    style: "width:100%;height:8px;background:#1a1a1a;border-radius:4px;overflow:hidden;margin-bottom:6px;",
  });
  const barFill = el("div", {
    style: "width:0%;height:100%;background:var(--color-accent, #5a7fdb);border-radius:4px;transition:width 0.3s ease;",
    "data-testid": "progress-bar-fill",
  });
  barContainer.appendChild(barFill);

  // Stage / status info
  const info = el("div", {
    style: "display:flex;flex-wrap:wrap;gap:4px 12px;font-size:10px;color:#aaa;",
  });

  const stageEl = el("span", { "data-testid": "progress-stage" });
  const nodesEl = el("span", { "data-testid": "progress-nodes" });
  const elapsedEl = el("span", { "data-testid": "progress-elapsed" });
  const stepEl = el("span", { "data-testid": "progress-step" });
  const queueEl = el("span", { "data-testid": "progress-queue" });

  info.appendChild(stageEl);
  info.appendChild(nodesEl);
  info.appendChild(elapsedEl);
  info.appendChild(stepEl);
  info.appendChild(queueEl);

  section.appendChild(barContainer);
  section.appendChild(info);

  // Determine stage display text
  var stageLabel = "Starting...";
  if (runState.status === "queued") stageLabel = "Queued";
  else if (runState.status === "in_progress") stageLabel = "Generating";
  else if (runState.status === "running") stageLabel = "Running";
  else if (runState.status === "submitted") stageLabel = "Submitted";
  else if (runState.status === "waiting") stageLabel = "Waiting";

  stageEl.textContent = "Stage: " + stageLabel;
  if (runState.totalNodes != null && runState.totalNodes > 0) {
    nodesEl.textContent = "Nodes: " + (runState.completedNodes || 0) + "/" + runState.totalNodes;
  } else {
    nodesEl.style.display = "none";
  }
  var samplerPct = runState.samplerPercent != null ? " (" + Math.round(runState.samplerPercent) + "%)" : "";
  stepEl.textContent = "Sampler: " + (runState.samplerStep != null ? runState.samplerStep : 0) + "/" + (runState.samplerMaximum || 0) + samplerPct;
  elapsedEl.textContent = "Elapsed: " + _formatDuration(runState.elapsedMs);

  if (runState.queuePosition > 0) {
    queueEl.textContent = "Queue: " + runState.queuePosition;
    queueEl.style.display = "";
  } else {
    queueEl.style.display = "none";
  }

  // Update progress bar width
  if (runState.overallPercent != null) {
    barFill.style.width = Math.max(0, Math.min(100, runState.overallPercent)) + "%";
  } else {
    // Indeterminate: show a partial bar with animation
    barFill.style.width = "30%";
    barFill.style.animation = "cm-pb-pulse 1.6s ease-in-out infinite";
  }

  return section;
}

// â”€â”€ Legacy Experiment grid viewport â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Retired in Wave D: filmstrip experiments now open History V2 detail.

function _formatDuration(ms) {
  if (ms == null) return "0ms";
  // Safe numeric conversion â€” never call .toFixed on a non-number
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

// â”€â”€ DOM Progress Patch (avoids full page teardown for frequent updates) â”€â”€

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
    stageEl.textContent = "Stage: " + stageLabel;
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

  var stepEl = document.querySelector('[data-testid="progress-step"]');
  if (stepEl) {
    var sp = rs.samplerPercent != null ? " (" + Math.round(rs.samplerPercent) + "%)" : "";
    stepEl.textContent = "Sampler: " + (rs.samplerStep != null ? rs.samplerStep : 0) + "/" + (rs.samplerMaximum || 0) + sp;
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
    if (rs.overallPercent != null) {
      barFill.style.width = Math.max(0, Math.min(100, rs.overallPercent)) + "%";
      barFill.style.animation = "";
    } else {
      barFill.style.width = "30%";
      barFill.style.animation = "cm-pb-pulse 1.6s ease-in-out infinite";
    }
  }
}

// â”€â”€ Favorite Star â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
      // History V2 record â€” durable annotation authority
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

// â”€â”€ Note Editor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
      // History V2 record â€” durable annotation authority
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

// â”€â”€ Right Workspace â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderWorkspace(state, context) {
  // Shelf: the right-side workspace is the single result panel (output
  // canvas, progress, metadata, recent filmstrip) — never a movable card.
  const workspace = el("div", { class: "comfymodal-studio-workspace", "data-testid": "workspace", "data-shelf-output-panel": "true" });

  // Feature tabs
  workspace.appendChild(renderFeatureTabs(state, context));

  // Canvas area
  workspace.appendChild(renderCanvas(state, context));

  // Progress section (shared progress display)
  workspace.appendChild(renderProgressSection(state, context));

  // Metadata section
  workspace.appendChild(renderMetadataSection(state, context));

  // Recent runs filmstrip
  workspace.appendChild(renderFilmstrip(state, context));

  return workspace;
}

// â”€â”€ Feature Tabs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€ Canvas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderCanvas(state, context) {
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const currentSpec = FEATURE_SPECS.find((f) => f.id === currentFeatureId);

  const canvas = el("div", {
    class: "comfymodal-studio-canvas",
    "data-testid": "canvas-area",
  });

  const outputUrl = state.playground && state.playground.lastRunOutput;
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
  } else if (outputUrl) {
    const img = el("img", {
      src: outputUrl,
      style: "max-width:100%;max-height:100%;object-fit:contain;border-radius:4px;",
      "data-testid": "canvas-output",
    });
    canvas.appendChild(img);
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
      text: "Generated output will appear here.",
      style: "color:var(--color-text-muted);",
    }));
  }

  return canvas;
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

// â”€â”€ Metadata Section â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//
// Compact metadata section tied to the selected canvas run with summary
// and collapsible advanced details.

function renderMetadataSection(state, context) {
  const section = el("div", {
    class: "comfymodal-studio-metadata-section",
    "data-testid": "metadata-section",
  });

  const apiBase = (context && context.apiBase) || "/comfymodal";
  const actions = buildActions(state, context);

  const selectedRun = state.playground && state.playground._selectedRun;
  if (!selectedRun) {
    // No run selected â€” show only when a canvas result exists
    return section;
  }

  const nr = selectedRun;
  const rc = nr.resolvedControls || {};
  const rqc = nr.requestedControls || {};
  const isFailed = nr.status === "error" || nr.status === "failed";

  // â”€â”€ Summary block â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Save Output (single-output backend action) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // Button visibility follows the record's saved state; the request
  // targets only the selected (primary) output.
  if (nr._historyKind === "generation") {
    // History V2 record â€” export through the repository by asset id
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

  // â”€â”€ Timing Summary Card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Key generation settings (using shared normalizer) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Collapsible toggles (Note | Advanced) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Note panel (collapsible) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const notePanel = el("div", {
    class: "comfymodal-studio-metadata-note-panel",
    style: "display:none;",
  });
  notePanel.appendChild(renderNoteEditor(nr, actions, apiBase));
  section.appendChild(notePanel);

  // â”€â”€ Advanced panel (collapsible) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const advancedPanel = el("div", {
    class: "comfymodal-studio-metadata-advanced",
    style: "display:none;font-size:10px;color:#666;",
  });

  const advancedItems = [];

  // IDs
  if (nr.id) advancedItems.push({ label: "Run ID", value: nr.id });
  if (nr.experimentId) advancedItems.push({ label: "Experiment ID", value: nr.experimentId });
  if (nr.snapshotId) advancedItems.push({ label: "Snapshot ID", value: nr.snapshotId });

  // Full timings â€” keep raw JSON accessible in advanced diagnostics
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

    // Waterfall summary (serialized v2 report) â€” same display text as
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

// â”€â”€ Carousel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//
// Image carousel of thumbnails from recent image-producing runs.
// Clicking a thumbnail updates the main canvas output.
// Only image-producing runs are shown.

// ── Carousel accessible naming (Phase I8) ─────────────────────────────────
//
// Every filmstrip button needs a distinguishable accessible name built from
// stable run context — preset label, truthful status, wall-clock time — and
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
    // Phase I8: user-cleared is an ordinary empty state — shared primitive.
    carousel.appendChild(renderEmptyState({
      title: "Recent runs cleared.",
      detail: "Submit a new run to see results here.",
      testid: "playground-recent-runs-cleared",
    }));
    return carousel;
  }

  if (recentRuns == null) {
    // Phase I8: loading is NOT an empty state — shared loading primitive.
    carousel.appendChild(renderLoadingState({
      label: "Loading recent runs…",
      size: "inline",
      testid: "playground-recent-runs-loading",
    }));

    // Async fetch fills cache â€” on next render it will show
    refreshRecentRuns(apiBase).then(function () {
      if (carousel.isConnected) rerender();
    });
  } else {
    // â”€â”€ Hidden state: show reveal bar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    // â”€â”€ Empty state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if (recentRuns.length === 0) {
      // Phase I8: shared generic empty-state primitive.
      carousel.appendChild(renderEmptyState({
        title: "Recent runs will appear here once you use the Playground.",
        testid: "playground-recent-runs-empty",
      }));
      return carousel;
    }

    // â”€â”€ Header row with actions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    const header = el("div", { class: "comfymodal-studio-carousel-header" });
    header.appendChild(el("span", {
      class: "comfymodal-studio-carousel-header-label",
      text: "Recent runs",
    }));

    const actions = el("div", { class: "comfymodal-studio-carousel-actions" });

    // Clear button â€” removes all cached and persisted runs
    actions.appendChild(el("button", {
      type: "button",
      class: "comfymodal-studio-carousel-btn danger",
      text: "Clear",
      title: "Remove all recent runs",
      onclick: function () {
        clearRecentRunsCache();
        clearAllRunResults();
        setCarouselCleared(true);
        rerender();
      },
    }));

    // Close button â€” hides the carousel (per-session)
    actions.appendChild(el("button", {
      type: "button",
      class: "comfymodal-studio-carousel-btn close-btn",
      text: "\u2715",
      "aria-label": "Hide recent runs",
      title: "Hide recent runs",
      onclick: function () {
        if (state.playground) {
          state.playground._carouselHidden = true;
          rerender();
        }
      },
    }));

    header.appendChild(actions);
    carousel.appendChild(header);

    // Carousel track for horizontal scrolling
    const track = el("div", { class: "comfymodal-studio-carousel-track" });

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
        "data-expid": isExperiment ? nr.experimentId : "",
        onclick: function () {
          if (isExperiment && nr.experimentId) {
            // H13: open the durable History V2 owner â€” never the legacy grid.
            requestHistoryRecordFocus(nr.experimentId, "experiment");
            if (context && context.setPage) context.setPage("history");
          } else if (imageUrl && state.playground) {
            // Ordinary run â€” update canvas with this run's output
            state.playground.lastRunOutput = imageUrl;
            state.playground._selectedRun = nr;
            rerender();
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

// ── Shelf Playground (Studio Workflow effort, leaf 1.2.2) ────────────────
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
// - Every other bound field: drag-handle reorder, Advanced placement,
//   same-row grouping, autosaved workflow-type layout with a subtle
//   autosaved indicator (no Save button).
// - Workflow switching goes through the shared picker
//   (web/studio-workflow-picker.js) with a reuse-values prompt; the old
//   output is marked stale until a new run completes.
// - Field renderers come from web/studio-field-blocks.js and role names
//   from web/studio-bindable-inputs.js — no duplicated catalog here.
// - Normal field values + layout autosave durably (studio-playground-state
//   Shelf lane); experiment-only state lives in the separate local draft
//   lane and never overwrites Workflow values.

var _SHELF_TYPE = "t2i";

// Mapped roles that are deliberately NOT rendered as Shelf fields. These are
// model-loader inputs: the files are chosen in the Model Library and already
// flow through the version's executable prompt, so an editable field here only
// invited a second, conflicting place to change the model stack.
var _SHELF_HIDDEN_ROLES = ["model_unet", "clip", "vae", "model", "model_clip", "model_vae"];
var _SHELF_SAVE_DELAY_MS = 300;

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

// Catalog-owned role name. Unknown schema roles fall back to the mapping
// display_name (backend truth) — never a second hardcoded name table.
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

// Mapping control_kind → fixed field-block kind (studio-field-blocks.js).
function _shelfBlockKind(entry) {
  var kind = entry && entry.control_kind;
  if (kind === "multiline") return "multiline";
  if (kind === "integer") return "integer";
  if (kind === "number" || kind === "float") return "float";
  if (kind === "enum") return "dropdown";
  if (kind === "file" || kind === "image" || kind === "model") return "model-picker";
  if (entry && Array.isArray(entry.enum_options) && entry.enum_options.length) return "dropdown";
  return "";
}

function _shelfRenderInput(role, entry, value, onChange) {
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
  var saved = loadShelfLayout(_SHELF_TYPE) || { order: [], rows: {}, advanced: [] };
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
  return { order: order, rows: rows, advanced: advanced, maxRow: maxRow };
}

function _shelfPersistLayout(layout) {
  saveShelfLayout(_SHELF_TYPE, { order: layout.order, rows: layout.rows, advanced: layout.advanced });
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
// schema-known roles are applied, then re-validated — never invents keys.
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
      text: "\u22ee\u22ee",
      title: "Drag to reorder",
    });
    grip.setAttribute("draggable", "true");
    grip.setAttribute("aria-label", "Drag to reorder " + _shelfDisplayName(role, entry));
    grip.addEventListener("dragstart", function (ev) {
      try {
        ev.dataTransfer.setData("text/shelf-role", role);
        ev.dataTransfer.effectAllowed = "move";
      } catch (e) { /* clipboard-less DnD still works via drop target */ }
      card.classList.add("is-dragging");
    });
    grip.addEventListener("dragend", function () {
      card.classList.remove("is-dragging");
      Array.prototype.forEach.call(document.querySelectorAll(".comfymodal-studio-shelf-card.is-drop-target"), function (n) {
        n.classList.remove("is-drop-target");
      });
    });
    head.appendChild(grip);
  }
  head.appendChild(el("span", {
    class: "comfymodal-studio-shelf-card-label",
    text: _shelfDisplayName(role, entry),
  }));
  if (!fixed) {
    var inAdvanced = layout.advanced.indexOf(role) !== -1;
    var groupBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-studio-shelf-mini-btn",
      "data-testid": "shelf-group-" + role,
      text: "Same row",
      title: "Group with the previous card in the same row",
    });
    groupBtn.setAttribute("aria-pressed", "false");
    groupBtn.addEventListener("click", function () {
      _shelfToggleGroup(state, context, actions, role);
    });
    head.appendChild(groupBtn);
    var advBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn comfymodal-studio-shelf-mini-btn" + (inAdvanced ? " is-on" : ""),
      "data-testid": "shelf-advanced-" + role,
      text: "Advanced",
      title: inAdvanced ? "Remove from Advanced" : "Move to Advanced",
    });
    advBtn.setAttribute("aria-pressed", inAdvanced ? "true" : "false");
    advBtn.addEventListener("click", function () {
      _shelfToggleAdvanced(state, context, actions, role);
    });
    head.appendChild(advBtn);
  }
  card.appendChild(head);

  card.addEventListener("dragover", function (ev) {
    if (fixed) return;
    ev.preventDefault();
    try { ev.dataTransfer.dropEffect = "move"; } catch (e) {}
    card.classList.add("is-drop-target");
  });
  card.addEventListener("dragleave", function () {
    card.classList.remove("is-drop-target");
  });
  card.addEventListener("drop", function (ev) {
    if (fixed) return;
    ev.preventDefault();
    ev.stopPropagation();
    var dragged = "";
    try { dragged = ev.dataTransfer.getData("text/shelf-role"); } catch (e) {}
    card.classList.remove("is-drop-target");
    if (dragged && dragged !== role) _shelfMoveBefore(state, context, actions, dragged, role);
  });

  var body = el("div", { class: "comfymodal-studio-shelf-card-body" });
  body.appendChild(_shelfRenderInput(role, entry, value, function (next) {
    commitShelfValue(state, context, actions, role, next);
  }));
  card.appendChild(body);
  return card;
}

function _shelfToggleAdvanced(state, context, actions, role) {
  var entries = _shelfEntries(state);
  var promptRole = _shelfPromptRole(entries);
  if (!role || role === promptRole) return;
  var layout = _shelfLayoutFor(entries, promptRole);
  var idx = layout.advanced.indexOf(role);
  if (idx === -1) layout.advanced.push(role);
  else layout.advanced.splice(idx, 1);
  _shelfPersistLayout(layout);
  _refreshShelfSection(state, context, actions);
}

function _shelfToggleGroup(state, context, actions, role) {
  var entries = _shelfEntries(state);
  var promptRole = _shelfPromptRole(entries);
  if (!role || role === promptRole) return;
  var layout = _shelfLayoutFor(entries, promptRole);
  var visible = layout.order.filter(function (r) { return layout.advanced.indexOf(r) === -1; });
  var pos = visible.indexOf(role);
  if (pos <= 0) return;
  var prev = visible[pos - 1];
  if (layout.rows[role] === layout.rows[prev]) {
    // Already grouped: assign a fresh row (ungroup).
    layout.maxRow += 1;
    layout.rows[role] = layout.maxRow;
  } else {
    layout.rows[role] = layout.rows[prev];
  }
  _shelfPersistLayout(layout);
  _refreshShelfSection(state, context, actions);
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
  if (targetRow != null && Number.isFinite(Number(targetRow))) {
    layout.rows[dragged] = Number(targetRow);
    if (Number(targetRow) > layout.maxRow) layout.maxRow = Number(targetRow);
  }
  _shelfPersistLayout(layout);
  _refreshShelfSection(state, context, actions);
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

  var head = el("div", { class: "comfymodal-studio-shelf-head" });
  head.appendChild(el("span", {
    class: "comfymodal-studio-shelf-workflow-name",
    "data-testid": "shelf-workflow-name",
    text: store.workflowName || store.workflowId,
  }));
  var switchBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn comfymodal-studio-shelf-mini-btn",
    "data-testid": "shelf-workflow-switch",
    text: "Change",
    title: "Switch Workflow via the shared picker",
  });
  switchBtn.addEventListener("click", function () {
    _openShelfPickerDialog(state, context, actions);
  });
  head.appendChild(switchBtn);
  // Subtle autosaved indicator — layout and values persist automatically,
  // so the Shelf never renders a Save button.
  head.appendChild(el("span", {
    class: "comfymodal-studio-shelf-autosaved",
    "data-testid": "shelf-autosaved",
    text: "Autosaved",
    title: "Field layout and values save automatically — no Save button needed.",
  }));
  section.appendChild(head);

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

  if (layout.advanced.length) {
    var advWrap = el("div", { class: "comfymodal-studio-shelf-advanced-wrap" });
    var advToggle = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn",
      "data-testid": "shelf-advanced-toggle",
      text: "Advanced (" + layout.advanced.length + ")",
    });
    advToggle.setAttribute("aria-expanded", "false");
    var advBox = el("div", {
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

// ── Shelf Workflow switching (shared picker + reuse prompt) ─────────────

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
    var mod = await import("./studio-backend-api.js");
    var ctxRes = await mod.getWorkflowRunContext(apiBase, nextId);
    var rawSchema = (ctxRes && ctxRes.control_schema) || {};
    // Array-shaped (mock) or role-keyed (backend) — accept both.
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
  }
  // Old output stays visible but stale until a new run completes.
  if (hadOutput) pg._shelfStaleOutput = true;
  if (context && context.setPage) context.setPage("playground");
}
