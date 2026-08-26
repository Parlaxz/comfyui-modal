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
import { getRuntimePresets } from "./studio-backend.js";
import { runStudioPreset, getStudioRunStatus, stopExperiment, listModels } from "./studio-backend-api.js";
import { loadModalOptions } from "./studio-output-preferences.js";

import {
  getVisibleControlsForPreset,
  getPresetCapabilitySummary,
  getUnavailableControlReasons,
} from "./studio-preset-capabilities.js";
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

// â”€â”€ Hydration helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
//
// Restore saved selection, fetch presets + history, validate preset,
// restore latest completed run preview plus draft/snapshot defaults.

export async function hydratePlayground(state, context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // 1. Load saved selection from localStorage
  const saved = loadSelection();

  // 2. Fetch runtime presets
  let presets = [];
  try {
    const { listPresets } = await import("./studio-backend-api.js");
    presets = await listPresets(apiBase) || [];
  } catch (e) {
    presets = [];
  }

  // 3. Determine feature ID (saved > default)
  const featureId = (saved && saved.featureId) || "txt2img";
  if (state.playground) {
    state.playground.featureId = featureId;
  }

  // 4. Determine preset ID (saved > empty)
  let targetPresetId = (saved && saved.presetId) || "";

  // 5. Validate preset exists
  const presetExists = targetPresetId && presets.some(function (p) {
    return (p.id || p.label || "") === targetPresetId;
  });

  if (!presetExists) {
    // Invalid/deleted preset â€” try another runnable preset first
    if (targetPresetId) {
      const otherRunnable = presets.find(function (p) {
        return (p.id || p.label || "") !== targetPresetId && p.status === "runnable";
      });
      if (otherRunnable) {
        targetPresetId = otherRunnable.id || otherRunnable.label || "";
        if (state.playground) {
          state.playground.selectedBackendId = targetPresetId;
        }
        saveSelection(targetPresetId, featureId);
      } else {
        clearSelection();
        targetPresetId = "";
        if (state.playground) {
          state.playground.selectedBackendId = "";
        }
      }
    }
  } else {
    if (state.playground) {
      state.playground.selectedBackendId = targetPresetId;
    }
  }

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

  // 6b. Hydrate control values from persisted draft or preset snapshot defaults
  const preset = presets.find(function (p) { return (p.id || p.label || "") === targetPresetId; });
  if (preset) {
    state.playground._currentPreset = preset;
  }
  hydrateControlsForSelection(state, targetPresetId, featureId, preset);

  // 7. Persist the resolved selection
  if (targetPresetId) {
    saveSelection(targetPresetId, featureId);
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
  // Scoped trackers are created in doRunSubmit (single runs) and in the
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

  // â”€â”€ Backend Selector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  panel.appendChild(renderControlGroup("Backend", renderBackendSelector(state, actions, context)));

  // â”€â”€ Workflow Selector (modern workflow-driven runs) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // Separate container rendered after the legacy selector row so legacy
  // test-ids/order stay intact. Empty-state only until a workflow is chosen.
  panel.appendChild(renderWorkflowSelector(state, context, actions));

  // â”€â”€ Preset-driven Controls â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const controlsContainer = el("div", { class: "comfymodal-studio-controls", "data-testid": "controls-container" });
  // Phase I8: section-level loading uses the shared primitive (legal DOM
  // container — it is fully replaced once capabilities resolve).
  controlsContainer.appendChild(renderLoadingState({
    label: "Loading preset capabilities…",
    size: "inline",
    testid: "playground-capabilities-loading",
  }));

  const selectedPresetId = state.playground && state.playground.selectedBackendId;
  if (selectedPresetId) {
    const currentPreset = getCurrentPresetForSelection(state, selectedPresetId);
    if (currentPreset) {
      hydrateControlsForSelection(state, selectedPresetId, currentFeatureId, currentPreset);
    }
  } else {
    state.playground._hydratedControls = {};
  }

  // Async load presets to derive capabilities
  getRuntimePresets({ apiBase }).then((presets) => {
    if (!controlsContainer.isConnected) return;
    while (controlsContainer.firstChild) controlsContainer.removeChild(controlsContainer.firstChild);

    const preset = (presets || []).find((p) => (p.id || p.label || "") === selectedPresetId);

    if (preset) {
      state.playground._currentPreset = preset;
    }

    if (!selectedPresetId || !preset) {
      // No preset selected â€” prompt to select one
      const noPresetMsg = el("div", {
        class: "comfymodal-studio-card",
        style: "padding:12px;text-align:center;",
      }, [
        el("p", {
          text: "Select a Backend Preset to see controls.",
          style: "font-size:11px;color:#888;margin:0 0 8px;",
        }),
        el("a", {
          text: "Open Backend to create presets",
          style: "font-size:11px;color:var(--color-accent);cursor:pointer;",
          onclick: (e) => {
            e.preventDefault();
            if (actions && actions.navigateToBackendTab) actions.navigateToBackendTab();
          },
        }),
      ]);
      controlsContainer.appendChild(noPresetMsg);
      return;
    }

    // Feature compatibility check
    const compat = preset.compatibleFeatures || [];
    if (!compat.includes(currentFeatureId)) {
      controlsContainer.appendChild(el("p", {
        text: `Selected preset does not support "${currentFeatureId}".`,
        style: "font-size:11px;color:#fbbf24;padding:8px;",
      }));
      return;
    }

    // Derive visible controls from capabilities + bindings
    const visibleControlIds = getVisibleControlsForPreset(preset, currentFeatureId);
    const summary = getPresetCapabilitySummary(preset, currentFeatureId);
    const reasons = getUnavailableControlReasons(preset, currentFeatureId);

    // If feature is a placeholder (object_remove/replace), show honest disabled state
    if (currentSpec.isPlaceholder) {
      const placeholderMsg = el("div", { class: "comfymodal-studio-placeholder-notice" }, [
        el("p", {
          text: currentSpec.placeholderReason || "This feature is not implemented yet.",
          style: "color:var(--color-text-muted);font-size:var(--font-size-sm);font-style:italic;",
        }),
      ]);
      controlsContainer.appendChild(placeholderMsg);
    }

    // Render visible controls
    visibleControlIds.forEach((ctrlId) => {
      const def = CONTROL_DEFS[ctrlId];
      if (!def) return;

      // Instruction is only visible for placeholder features (object_remove/object_replace)
      if (ctrlId === "instruction" && !currentSpec.isPlaceholder) return;

      const isBound = summary.requiredBindings.some((r) => r.key === ctrlId && r.bound)
        || summary.optionalBindings.some((o) => o.key === ctrlId && o.bound);

      // Check if this control is in the preset's nodeBindings
      const hasBinding = !!(preset.nodeBindings && preset.nodeBindings[ctrlId] && preset.nodeBindings[ctrlId].nodeId);
      const hasResolvedSchema = !!(
        preset.controlSchemas
        && preset.controlSchemas[ctrlId]
        && preset.controlSchemas[ctrlId].schemaResolved
      );

      const controlRow = renderControl(def, state, actions, preset);

      // Disable the control if it's a required binding not yet bound
      if (!isBound && !hasBinding && !hasResolvedSchema) {
        controlRow.style.opacity = "0.5";
        const reason = reasons[ctrlId] || "Requires node binding";
        const reasonEl = el("p", {
          text: `\u26a0 ${reason}`,
          style: "font-size:9px;color:#fbbf24;margin:2px 0 0;",
        });
        controlRow.appendChild(reasonEl);
      }

      // In experiment mode, add axis checkbox for eligible controls
      if (isExperiment && def.experimentEligible) {
        const checkboxWrapper = enhanceControlWithAxisCheckbox(controlRow, ctrlId, state, actions);
        if (checkboxWrapper && controlRow.firstChild) {
          controlRow.insertBefore(checkboxWrapper, controlRow.firstChild);
        }
        const axisData = state.playground && state.playground.experimentAxes && state.playground.experimentAxes[ctrlId];
        const eligibleAxes = (state.playground && state.playground._eligibleAxes) || [];
        if (axisData && axisData.enabled && eligibleAxes.includes(ctrlId)) {
          const originalInput = controlRow.querySelector('[data-testid="input-' + ctrlId + '"]');
          if (originalInput) originalInput.remove();
        }
      }

      controlsContainer.appendChild(controlRow);
    });

    // If no visible controls (shouldn't normally happen), show a message
    if (visibleControlIds.length === 0 && !currentSpec.isPlaceholder) {
      controlsContainer.appendChild(el("p", {
        text: "No controls available for this preset+feature combination.",
        style: "font-size:11px;color:#888;padding:8px;font-style:italic;",
      }));
    }
  }).catch(() => {
    if (!controlsContainer.isConnected) return;
    while (controlsContainer.firstChild) controlsContainer.removeChild(controlsContainer.firstChild);
    controlsContainer.appendChild(el("p", {
      text: "Could not load preset data.",
      style: "font-size:11px;color:#f87171;padding:8px;",
    }));
  }).then(() => {
    if (!panel.isConnected) return;
    const pg = state.playground;
    if (pg && pg._controlPanelScrollRestorePending && pg._controlPanelScrollTop != null) {
      panel.scrollTop = pg._controlPanelScrollTop;
      if (panel.scrollTop === pg._controlPanelScrollTop) {
        pg._controlPanelScrollRestorePending = false;
      }
    }
  });

  panel.appendChild(controlsContainer);

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

function renderBackendSelector(state, actions, context) {
  const container = el("div", { class: "comfymodal-studio-backend-selector", "data-testid": "backend-selector" });

  const select = el("select", {
    class: "comfymodal-input comfymodal-studio-select",
    "data-testid": "backend-select",
  });
  select.addEventListener("mousedown", () => {
    if (state.playground) state.playground._backendSelectInteracting = true;
  });
  select.addEventListener("focus", () => {
    if (state.playground) state.playground._backendSelectInteracting = true;
  });
  select.addEventListener("blur", () => {
    if (state.playground) state.playground._backendSelectInteracting = false;
  });
  const loadingOpt = el("option", { value: "", text: "Loading backends…", disabled: true, selected: true });
  select.appendChild(loadingOpt);
  select.disabled = true;
  container.appendChild(select);

    // Async load presets through the Studio abstraction (runtime selectors only)
  const apiBase = (context && context.apiBase) || "/comfymodal";
  getRuntimePresets({ apiBase }).then((backends) => {
    if (!select.isConnected) return;
    while (select.firstChild) select.removeChild(select.firstChild);

    if (!backends || backends.length === 0) {
      // Empty state: show disabled select + link to Backend tab
      const emptyOpt = el("option", { value: "", text: "No backends available", disabled: true, selected: true });
      select.appendChild(emptyOpt);
      select.disabled = true;

      // Remove any existing empty message and add fresh one linking to Backend tab
      const existingMsg = container.querySelector(".comfymodal-studio-backend-empty-msg");
      if (existingMsg) existingMsg.remove();

      // Phase I8: ordinary no-selection empty state via the shared primitive
      // (copy supplied here; the cleanup marker class is preserved).
      const backendLink = el("a", {
        text: "Go to Backend tab to add backends.",
        style: "color:var(--color-accent);cursor:pointer;",
        onclick: (e) => {
          e.preventDefault();
          if (actions && actions.navigateToBackendTab) actions.navigateToBackendTab();
        },
      });
      const emptyMsg = renderEmptyState({
        title: "No backends configured.",
        action: backendLink,
        testid: "playground-backend-empty",
      });
      emptyMsg.classList.add("comfymodal-studio-backend-empty-msg");
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
    if (!select.isConnected) return;
    while (select.firstChild) select.removeChild(select.firstChild);
    const errOpt = el("option", { value: "", text: "Could not load backends", disabled: true, selected: true });
    select.appendChild(errOpt);
    select.disabled = true;
  });

  return container;
}

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

function _isModernRunSelected(state) {
  const store = state && state.playground && state.playground._workflowRun;
  return !!(store && store.workflowId && store.workflowVersionId);
}

function _workflowOptionLabel(w) {
  const name = (w && w.name) ? w.name : "Unnamed workflow";
  if (w && w.version_count != null) {
    return name + " (" + w.version_count + " version" + (w.version_count === 1 ? "" : "s") + ")";
  }
  if (w && w.latest_version_number != null) {
    return name + " (v" + w.latest_version_number + ")";
  }
  return name;
}

function _workflowVersionOptionLabel(v) {
  const label = "v" + (v && v.version_number != null ? v.version_number : "?");
  const created = (v && v.created_at) ? _workflowShortDate(v.created_at) : "";
  return created ? label + " \u00b7 " + created : label;
}

function _workflowShortDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  try {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch (e) {
    return String(iso);
  }
}

async function _loadWorkflowModelLibrary(state, apiBase) {
  try {
    if (_workflowModelLibraryCacheKey === apiBase && _workflowModelLibraryCache) {
      if (state && state.playground) state.playground._workflowModelLibrary = _workflowModelLibraryCache;
      return _workflowModelLibraryCache;
    }
    const data = await listModels(apiBase);
    const records = (data && Array.isArray(data.models)) ? data.models : [];
    _workflowModelLibraryCache = records;
    _workflowModelLibraryCacheKey = apiBase;
    if (state && state.playground) state.playground._workflowModelLibrary = records;
    return records;
  } catch (e) {
    if (state && state.playground) state.playground._workflowModelLibrary = [];
    return [];
  }
}

/**
 * True when the selected workflow/version declares a non-empty model
 * compatibility contract. With no declared contract every enum model is
 * treated as compatible (no suffix, no gating).
 */
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
  if (!store.workflowVersionId) return { text: "Select a version", color: "" };
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

function _workflowVersionSelectEl(state, actions, context) {
  const store = state && state.playground && state.playground._workflowRun;
  const select = el("select", {
    class: "comfymodal-input comfymodal-studio-select",
    "data-testid": "workflow-version-selector",
  });
  if (!store || !store.workflowId) {
    select.appendChild(el("option", { value: "", text: "No workflow selected", disabled: true, selected: true }));
    select.disabled = true;
    return select;
  }
  const placeholder = el("option", { value: "", text: "Select a version\u2026", disabled: true });
  if (!store.workflowVersionId) placeholder.selected = true;
  select.appendChild(placeholder);
  (store.versions || []).forEach((v) => {
    const opt = el("option", { value: String(v.workflow_version_id), text: _workflowVersionOptionLabel(v) });
    if (store.workflowVersionId && String(store.workflowVersionId) === String(v.workflow_version_id)) opt.selected = true;
    select.appendChild(opt);
  });
  select.disabled = !store.workflowId || (store.versions || []).length === 0;
  select.addEventListener("change", () => {
    _handleVersionChange(state, context, actions, select.value);
  });
  return select;
}

function _workflowPresetSelectEl(state, actions, context) {
  const store = state && state.playground && state.playground._workflowRun;
  const select = el("select", {
    class: "comfymodal-input comfymodal-studio-select",
    "data-testid": "workflow-preset-selector",
  });
  if (!store || !store.workflowVersionId) {
    select.appendChild(el("option", { value: "", text: "No version selected", disabled: true, selected: true }));
    select.disabled = true;
    return select;
  }
  const placeholder = el("option", { value: "", text: "Select a preset\u2026", disabled: true });
  if (!store.presetId) placeholder.selected = true;
  select.appendChild(placeholder);
  (store.presets || []).forEach((p) => {
    const opt = el("option", { value: String(p.preset_id), text: p.name || "Unnamed preset" });
    if (store.presetId && String(store.presetId) === String(p.preset_id)) opt.selected = true;
    select.appendChild(opt);
  });
  select.disabled = !store.workflowVersionId || (store.presets || []).length === 0;
  select.addEventListener("change", () => {
    _handlePresetChange(state, context, actions, select.value);
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

function _workflowControlRow(entry, schemaEntry, store, wf, state, actions, context, compat) {
  const role = entry.semantic_role;
  const group = el("div", {
    class: "comfymodal-studio-control-group",
    "data-testid": "workflow-control-" + role,
  });
  group.appendChild(el("label", { class: "comfymodal-studio-control-label", text: role }));

  const current = (store.controlValues && typeof store.controlValues === "object") ? store.controlValues : {};
  const hasValue = Object.prototype.hasOwnProperty.call(current, role);
  const value = hasValue ? current[role] : undefined;
  const kind = schemaEntry.control_kind || "string";
  const enumOptions = Array.isArray(schemaEntry.enum_options) ? schemaEntry.enum_options : [];
  const hasEnums = enumOptions.length > 0;
  // With no declared compatibility contract every enum model is treated as
  // compatible (no suffix, no gating).
  const hasModelContract = _workflowHasModelContract(store);

  // DOMâ†’store round-trip: preserve falsy values verbatim. Number inputs only
  // convert to Number when the schema kind is integer/float; selects produce
  // the exact option string (including "" if an option is empty string).
  function commit(rawValue) {
    store.setControlValue(role, rawValue);
    const schema = wf.getControlSchema(store);
    const validation = wf.validateMappedValues(store.controlValues || {}, schema);
    store.setControlValues(validation.values);
    const reasons = validation.errors && validation.errors.length
      ? validation.errors.map((e) => e.message)
      : [];
    // Known incompatible models must not silently execute: mirror the reason
    // in the store so every gating consumer sees it.
    const incompatible = _selectedIncompatibleModel(store, wf, compat);
    if (incompatible) {
      reasons.push("model '" + incompatible + "' is not compatible with this workflow version");
    }
    store.setReasons(reasons);
    _syncWorkflowGating(state, context, actions);
  }

  let input = null;

  if (kind === "enum" || hasEnums) {
    input = el("select", {
      class: "comfymodal-input comfymodal-studio-select",
      "data-testid": "workflow-input-" + role,
    });
    enumOptions.forEach((opt) => {
      let text = String(opt);
      if (hasModelContract && compat && compat.byFilename && Object.prototype.hasOwnProperty.call(compat.byFilename, String(opt))) {
        const c = compat.byFilename[String(opt)];
        if (c && c.compatible === false) {
          text = String(opt) + " (incompatible)";
        } else if (c && c.installed === false) {
          text = String(opt) + " (missing)";
        }
      }
      const option = el("option", { value: String(opt), text: text });
      if (value !== undefined && String(value) === String(opt)) option.selected = true;
      input.appendChild(option);
    });
    input.addEventListener("change", () => commit(input.value));
  } else if (kind === "boolean") {
    input = el("input", {
      type: "checkbox",
      class: "comfymodal-input comfymodal-studio-checkbox",
      "data-testid": "workflow-input-" + role,
    });
    input.checked = value === true || value === 1 || value === "1" || value === "true";
    input.addEventListener("change", () => commit(input.checked));
  } else if (kind === "integer") {
    input = el("input", {
      type: "number",
      step: "1",
      min: schemaEntry.minimum != null ? String(schemaEntry.minimum) : "",
      max: schemaEntry.maximum != null ? String(schemaEntry.maximum) : "",
      class: "comfymodal-input comfymodal-studio-number-input",
      value: value !== undefined && value !== null ? String(value) : "",
      "data-testid": "workflow-input-" + role,
    });
    input.addEventListener("input", () => {
      const raw = input.value;
      const parsed = parseInt(raw, 10);
      commit(raw === "" || Number.isNaN(parsed) ? raw : parsed);
    });
  } else if (kind === "number") {
    input = el("input", {
      type: "number",
      step: schemaEntry.step != null ? String(schemaEntry.step) : "any",
      min: schemaEntry.minimum != null ? String(schemaEntry.minimum) : "",
      max: schemaEntry.maximum != null ? String(schemaEntry.maximum) : "",
      class: "comfymodal-input comfymodal-studio-number-input",
      value: value !== undefined && value !== null ? String(value) : "",
      "data-testid": "workflow-input-" + role,
    });
    input.addEventListener("input", () => {
      const raw = input.value;
      const parsed = parseFloat(raw);
      commit(raw === "" || Number.isNaN(parsed) ? raw : parsed);
    });
  } else if (kind === "multiline") {
    input = el("textarea", {
      class: "comfymodal-input comfymodal-studio-textarea",
      value: value !== undefined && value !== null ? String(value) : "",
      "data-testid": "workflow-input-" + role,
    });
    input.addEventListener("input", () => commit(input.value));
  } else if (kind === "file" || kind === "image") {
    // Read-only display of the current filename (upload is out of scope);
    // the value stays whatever the preset/graph declared.
    input = el("input", {
      type: "text",
      class: "comfymodal-input comfymodal-studio-text-input",
      value: value !== undefined && value !== null ? String(value) : "",
      disabled: true,
      title: "File selection is out of scope — the current value comes from the preset/graph.",
      "data-testid": "workflow-input-" + role,
    });
    group.appendChild(el("span", {
      class: "comfymodal-studio-control-note",
      text: "File selection is out of scope — value preserved from preset/graph.",
      style: "font-size:var(--font-size-xs);color:var(--color-text-muted);",
    }));
  } else {
    input = el("input", {
      type: "text",
      class: "comfymodal-input comfymodal-studio-text-input",
      value: value !== undefined && value !== null ? String(value) : "",
      "data-testid": "workflow-input-" + role,
    });
    input.addEventListener("input", () => commit(input.value));
  }

  if (input) group.appendChild(input);
  return group;
}

function _renderWorkflowMappedControls(container, state, context, actions) {
  while (container.firstChild) container.removeChild(container.firstChild);
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf || !store.runContext || !store.runContext.mapping) return;
  const entries = Array.isArray(store.runContext.mapping.entries) ? store.runContext.mapping.entries : [];
  const schema = wf.getControlSchema(store);
  const modelRecords = (state && state.playground && state.playground._workflowModelLibrary) || [];
  const compat = wf.modelCompatibility(store, modelRecords);
  entries.forEach((entry) => {
    const role = entry && entry.semantic_role;
    if (!role || !Object.prototype.hasOwnProperty.call(schema, role)) return;
    const row = _workflowControlRow(entry, schema[role], store, wf, state, actions, context, compat);
    if (row) container.appendChild(row);
  });
}

function _populateWorkflowSelector(container, state, context, actions) {
  while (container.firstChild) container.removeChild(container.firstChild);
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;

  container.appendChild(_workflowSelectEl(state, actions, context));
  container.appendChild(_workflowVersionSelectEl(state, actions, context));
  container.appendChild(_workflowPresetSelectEl(state, actions, context));
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

  const controlsBox = el("div", { "data-testid": "workflow-mapped-controls" });
  _renderWorkflowMappedControls(controlsBox, state, context, actions);
  container.appendChild(controlsBox);
}

function _rerenderWorkflowSection(state, context, actions) {
  const container = document.querySelector('[data-testid="workflow-selector-section"]');
  if (!container) return;
  _populateWorkflowSelector(container, state, context, actions);
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
        _rerenderWorkflowSection(state, context, actions);
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
  store.setPresetId("");
  store.setWorkflowName("");
  store.setPresetName("");
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
  const missing = "Requested workflow/version/preset no longer available";

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
  if (handoff.presetId) {
    const presetExists = (store.presets || []).some((p) => String(p.preset_id) === String(handoff.presetId));
    if (!presetExists) {
      _failWorkflowHandoff(wf, store, missing);
      return;
    }
    const preRes = await wf.selectPreset(apiBase, store, handoff.presetId);
    if (!preRes.ok) {
      _failWorkflowHandoff(wf, store, preRes.error || missing);
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
    presetId: store.presetId,
    workflowName: store.workflowName || "",
    presetName: store.presetName || "",
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
    const verExists = (store.versions || []).some((v) => String(v.workflow_version_id) === String(saved.workflowVersionId));
    if (!verExists) {
      // Keep the workflow selected; never silently substitute a version.
      store.statusLine = "Requested version no longer available";
      store.setVersionId("");
      store.setPresetId("");
      store.setPresetName("");
      store.controlValues = {};
      store.setStatus("ready");
      store.setReasons(["Requested version no longer available"]);
      return;
    }
    const verRes = await wf.selectVersion(apiBase, store, saved.workflowVersionId);
    if (!verRes.ok) {
      store.statusLine = verRes.error || "Requested version no longer available";
      return;
    }
  }
  if (saved.presetId) {
    const presetExists = (store.presets || []).some((p) => String(p.preset_id) === String(saved.presetId));
    if (!presetExists) {
      // Keep the workflow/version; never silently substitute a preset.
      store.statusLine = "Requested preset no longer available";
      store.setPresetId("");
      store.setPresetName("");
      store.setStatus("ready");
      store.setReasons(["Requested preset no longer available"]);
      return;
    }
    const preRes = await wf.selectPreset(apiBase, store, saved.presetId);
    if (!preRes.ok) {
      store.statusLine = preRes.error || "Requested preset no longer available";
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
      presetId: store.presetId,
      workflowName: store.workflowName || "",
      presetName: store.presetName || "",
    });
  }
  _rerenderWorkflowSection(state, context, actions);
}

async function _handleVersionChange(state, context, actions, versionId) {
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf || !versionId) return;
  const apiBase = (context && context.apiBase) || "/comfymodal";
  store.handoffError = null;
  const result = await wf.selectVersion(apiBase, store, versionId);
  if (result && result.ok) {
    wf.saveWorkflowSelection({
      workflowId: store.workflowId,
      workflowVersionId: store.workflowVersionId,
      presetId: store.presetId,
      workflowName: store.workflowName || "",
      presetName: store.presetName || "",
    });
  }
  _rerenderWorkflowSection(state, context, actions);
}

async function _handlePresetChange(state, context, actions, presetId) {
  const store = state && state.playground && state.playground._workflowRun;
  const wf = state && state.playground && state.playground._workflowRunModule;
  if (!store || !wf) return;
  const apiBase = (context && context.apiBase) || "/comfymodal";
  store.handoffError = null;
  const result = await wf.selectPreset(apiBase, store, presetId || "");
  if (result && result.ok) {
    wf.saveWorkflowSelection({
      workflowId: store.workflowId,
      workflowVersionId: store.workflowVersionId,
      presetId: store.presetId,
      workflowName: store.workflowName || "",
      presetName: store.presetName || "",
    });
  }
  _rerenderWorkflowSection(state, context, actions);
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
    if (!ctxResult.ok || !store.runContext) {
      ctrl.applyLocalError("Workflow context unavailable; reselect the workflow");
      if (btn) { btn.disabled = false; btn.textContent = "Run"; }
      return;
    }
    _rerenderWorkflowSection(state, context, actions);
  }

  const schema = wf.getControlSchema(store);

  ctrl.mark("validation_start");
  const presetObj = (store.presets || []).find(function (p) {
    return String(p.preset_id) === String(store.presetId || "");
  }) || null;
  const merged = wf.mergePresetAndOverrides(presetObj, store.controlValues || {}, schema);
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
  const result = await runStudioPreset(apiBase, payload);
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

async function doRunSubmit(state, context, actions, clickedBtn) {
  // T0: request identity origin (literal first line, before any workflow prep)
  const requestId = crypto.randomUUID();
  const ui_run_triggered_wall_unix_ms = Date.now();
  const ui_run_triggered_perf_ms = performance.now();
  const browser_time_origin_ms = performance.timeOrigin;
  const requestOriginInfo = {
    request_id: requestId,
    trigger_source: "playground_run",
    ui_run_triggered_wall_unix_ms: ui_run_triggered_wall_unix_ms,
    ui_run_triggered_perf_ms: ui_run_triggered_perf_ms,
    browser_time_origin_ms: browser_time_origin_ms,
  };

  // â”€â”€ Modern workflow mode: never fall back to the legacy preset path â”€â”€
  // Prefer the actually-clicked button; fall back to the visible primary
  // run button (never an unscoped first-match that could be hidden/stale).
  if (_isModernRunSelected(state)) {
    var _modernBtn = clickedBtn || _resolvePrimaryRunButton();
    await _modernRunSubmit(state, context, actions, _modernBtn);
    return;
  }

  const apiBase = (context && context.apiBase) || "/comfymodal";
  var ctrl = _getRunController(state, actions);
  if (!ctrl) return;
  ctrl.beginRun();
  ctrl.mark("submit_entered");
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const selectedId = state.playground && state.playground.selectedBackendId;
  if (!selectedId) return;

  const { listPresets } = await import("./studio-backend-api.js");
  ctrl.mark("build_start");
  const presets = await listPresets(apiBase) || [];
  const preset = presets.find(function (p) { return (p.id || p.label || "") === selectedId; });
  if (!preset) return;
  ctrl.mark("build_end");

  const controls = buildEffectiveControls(state, preset, currentFeatureId);

  ctrl.mark("validation_start");
  const validationError = validateControls(controls, preset);
  ctrl.mark("validation_end");
  if (validationError) {
    ctrl.applyLocalError(validationError);
    return;
  }
  const modalOptions = await buildStudioModalOptions(apiBase);

  // Clear previous output so canvas shows live progress immediately
  if (state.playground) {
    state.playground.lastRunOutput = null;
    state.playground._selectedRun = null;
  }
  // Put determinate sampler fields into running state BEFORE remote call
  var _runSteps = controls.steps;
  var _runMaxSteps = (_runSteps != null && Number(_runSteps) > 0) ? Number(_runSteps) : 0;
  if (state.playground && state.playground.runState) delete state.playground.runState._localStartTime;
  // Start local elapsed timer immediately on press
  _startLocalElapsedTimer(state, context);

  // Capture client-side timestamps at press time (top-level `trace` for server)
  const t0_perf_ms = performance.now();
  const t0_now = Date.now();

  ctrl.mark("http_invoked");
  const result = await runStudioPreset(apiBase, {
    presetId: preset.id || selectedId,
    featureId: currentFeatureId,
    controls: controls,
    modal_options: modalOptions,
    request_origin: requestOriginInfo,
    metadata: {
      source: "studio_playground",
    },
    trace: {
      t0_perf_ms: t0_perf_ms,
      t0_perf_now_ms: t0_now,
      t0_client_press_ms: t0_now,
      request_id: requestId,
    },
  });
  ctrl.mark("backend_ack");

  if (result && result.status === "ok") {
    // â”€â”€ Direct run: result is already completed, no polling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if (_handleDirectRunResult(result, state, context, actions, controls)) {
      return;
    }

    // â”€â”€ Scheduler path: result is a submission, start polling â”€â”€â”€â”€â”€â”€â”€
    // Derive initial sampler maximum from submitted steps control
    var _submittedSteps = controls.steps;
    ctrl.setBackendIds(result.runId || result.experimentId, result.experimentId);
    ctrl.applySubmission({
      experimentId: result.experimentId || result.runId || "",
      samplerMaximum: (_submittedSteps != null && Number(_submittedSteps) > 0) ? Number(_submittedSteps) : 0,
    });
    ctrl.attachEventSource((context && context.comfyApi) || (context && context.api));

    // Restart local elapsed timer; preserves original _localStartTime
    _startLocalElapsedTimer(state, context);
  } else {
    const errMsg = (result && result.message) || "Run failed.";
    if (result && result.error_code) {
      console.error("[Studio run] execution failed", {
        error_code: result.error_code,
        error: result.error || null,
      });
    }
    ctrl.applyLocalError(errMsg);
  }
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
    // Prioritize doRunSubmit so prior image/metadata stays visible until
    // the new submission enters flight (setRunState("running") clears the
    // completed state and triggers re-render).
    btn.onclick = function () {
      doRunSubmit(state, context, actions, btn);
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
      doRunSubmit(state, context, actions, btn);
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
      doRunSubmit(state, context, actions, btn);
    };
    return container;
  }

  // Async-load presets to determine runnability
  getRuntimePresets({ apiBase }).then((presets) => {
    if (!container.isConnected) return;
    while (reason.firstChild) reason.removeChild(reason.firstChild);

    // Modern workflow mode: gating is driven by the workflow run store.
    // Never fall back to the legacy preset path when a workflow is selected.
    if (_isModernRunSelected(state)) {
      _applyModernRunButtonState(state, context, actions, btn, reason);
      return;
    }

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

    // â”€â”€ Single run mode (also used in experiment mode, since experiment
    //     mode has its own dedicated "Run Experiment" button) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        var ctrl = _getRunController(state, actions);

        // Build controls early so sampler fields are available for running state
        if (ctrl) ctrl.mark("build_start");
        const controls = buildEffectiveControls(state);
        if (ctrl) ctrl.mark("build_end");

        // Clear previous output so canvas shows live progress immediately
        state.playground.lastRunOutput = null;
        state.playground._selectedRun = null;

        // Put determinate sampler fields into running state BEFORE remote call
        var _runSteps = controls.steps;
        var _runMaxSteps = (_runSteps != null && Number(_runSteps) > 0) ? Number(_runSteps) : 0;
        if (ctrl) ctrl.beginRun({ samplerMaximum: _runMaxSteps });
        // Start local elapsed timer immediately on press
        _startLocalElapsedTimer(state, context);

        const validationError = validateControls(controls, preset);
        if (validationError) {
          btn.disabled = false;
          btn.textContent = "Run";
          if (ctrl) ctrl.applyLocalError(validationError);
          return;
        }
        const modalOptions = await buildStudioModalOptions(apiBase);

        // Capture client-side timestamps at press time (top-level `trace` for server)
        var t0_perf_ms = performance.now();
        var t0_now = Date.now();

        if (ctrl) ctrl.mark("http_invoked");
        const result = await runStudioPreset(apiBase, {
          presetId: preset.id || selectedId,
          featureId: currentFeatureId,
          controls: controls,
          modal_options: modalOptions,
          metadata: {
            source: "studio_playground",
          },
          trace: {
            t0_perf_ms: t0_perf_ms,
            t0_perf_now_ms: t0_now,
            t0_client_press_ms: t0_now,
          },
        });
        if (ctrl) ctrl.mark("backend_ack");

        if (result && result.status === "ok") {
          // â”€â”€ Direct run: result is already completed, no polling â”€â”€
          if (_handleDirectRunResult(result, state, context, actions, controls)) {
            return;
          }

          // â”€â”€ Scheduler path: submission, start polling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
          var _inlineSteps = controls.steps;
          if (ctrl) {
            ctrl.setBackendIds(result.runId || result.experimentId, result.experimentId);
            ctrl.applySubmission({
              experimentId: result.experimentId || result.runId || "",
              samplerMaximum: (_inlineSteps != null && Number(_inlineSteps) > 0) ? Number(_inlineSteps) : 0,
            });
            ctrl.attachEventSource((context && context.comfyApi) || (context && context.api));
          }

          // Restart local elapsed timer; preserves original _localStartTime
          _startLocalElapsedTimer(state, context);
        } else {
          const errMsg = (result && result.message) || "Run failed.";
          if (ctrl) ctrl.applyLocalError(errMsg);
        }
      };
    }
  }).catch(() => {
    if (!container.isConnected) return;
    if (_isModernRunSelected(state)) {
      while (reason.firstChild) reason.removeChild(reason.firstChild);
      _applyModernRunButtonState(state, context, actions, btn, reason);
      return;
    }
    while (reason.firstChild) reason.removeChild(reason.firstChild);
    reason.appendChild(el("p", {
      text: "Could not load presets.",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    }));
  });

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
    // Show completed/error state in metadata section instead
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
  const workspace = el("div", { class: "comfymodal-studio-workspace", "data-testid": "workspace" });

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
