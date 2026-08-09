// Modal Studio — Playground
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
import { runStudioPreset, getStudioRunStatus, stopExperiment, getModalConfig } from "./studio-backend-api.js";

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
import { createScopedTracker } from "./comfymodal-progress.js";
import { updateRunAnnotation, saveRunOutput } from "./studio-backend-api.js";

async function buildStudioModalOptions(apiBase) {
  const config = await getModalConfig(apiBase);
  const saved = window._comfyModalOutputOptions || {};
  const mode = (config && config.execution_mode) || window._comfyModalExecutionMode || "v2";
  window._comfyModalExecutionMode = mode;
  return {
    execution_mode: mode,
    output_format: config && config.output_format !== undefined ? config.output_format : (saved.output_format || "original"),
    quality: config && config.quality !== undefined ? config.quality : (saved.quality || 75),
    webp_lossless_compression: config && config.webp_lossless_compression !== undefined
      ? config.webp_lossless_compression : (saved.webp_lossless_compression || "balanced"),
    auto_save_local: config && config.auto_save_local !== undefined ? !!config.auto_save_local : !!saved.auto_save_local,
    save_folder: config && config.save_folder !== undefined ? config.save_folder : (saved.save_folder || ""),
    save_metadata_sidecar: config && config.save_metadata_sidecar !== undefined
      ? config.save_metadata_sidecar !== false : saved.save_metadata_sidecar !== false,
  };
}
import { el, createZoomableImageEl, createImagePreviewOverlay } from "./studio-ui.js";

// ── Polling helper for experiment status ──────────────────────────────────
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
      if (actions && actions.setRunState) {
        actions.setRunState({
          status: "error",
          message: "Experiment timed out after 5 minutes.",
        });
      }
      return;
    }

    let data;
    try {
      data = await getStudioRunStatus(apiBase, experimentId);
    } catch (err) {
      // Transient fetch error — stay in waiting state until deadline
      if (actions && actions.setRunState) {
        actions.setRunState({ status: "waiting", experimentId });
      }
      return;
    }

    if (!data) {
      // Null/empty response — stay in waiting state
      if (actions && actions.setRunState) {
        actions.setRunState({ status: "waiting", experimentId });
      }
      return;
    }

    // Server-level error response
    if (data.status && data.status !== "ok") {
      _stopPolling(state);
      const errMsg = (data.message || data.error || "Run failed.").substring(0, 200);
      if (actions && actions.setRunState) {
        actions.setRunState({ status: "error", message: errMsg });
      }
      return;
    }

    // Unknown experiment (no definition yet or invalid id)
    if (!data.definition && (!data.snapshot || Object.keys(data.snapshot).length === 0)) {
      // Experiment not yet available — stay in waiting / submitted state
      if (actions && actions.setRunState) {
        actions.setRunState({ status: "waiting", experimentId });
      }
      return;
    }

    const snapshot = data.snapshot || {};
    const status = snapshot.overall_status || snapshot.status || data.state || "";
    const counters = snapshot.counters || {};
    const events = data.events || [];

    // Check for explicit terminal event evidence in the journal
    const hasTerminalEvent = events.some(function (ev) {
      return ev.type === "experiment.completed" ||
             ev.type === "experiment.stopped" ||
             ev.type === "experiment.cancelled";
    });

    // Check for explicit error events in the journal (safety net for
    // scheduler failures that may not yet be reflected in snapshot status)
    const errorEvents = events.filter(function (ev) {
      return ev.type === "experiment.error" || ev.type === "experiment.failed_fatal";
    });
    const hasExplicitErrorEvent = errorEvents.length > 0;
    const lastErrorMsg = hasExplicitErrorEvent
      ? (errorEvents[errorEvents.length - 1].payload || {}).error || ""
      : "";

    // Cell-level completion evidence
    const completedCellCount = counters.completed || 0;
    const totalCells = snapshot.total_cells || 0;
    const cellCompletedEvents = events.filter(function (ev) {
      return ev.type === "cell.completed";
    }).length;
    const hasCellCompletionEvidence = completedCellCount > 0 || cellCompletedEvents > 0;

    // Build cell output URL map from cell.completed events so the grid
    // can show individual thumbnails in their correct axis position.
    var _pollCellOutputs = _buildCellOutputMap(events, apiBase);

    if (status === "queued") {
      if (actions && actions.setRunState) {
        actions.setRunState({
          status: "queued",
          experimentId,
          _snapshot: snapshot,
          _events: events,
          _cellOutputs: _pollCellOutputs,
        });
      }
    } else if (status === "in_progress" || status === "running") {
      const progressState = {
        status: "in_progress",
        experimentId,
        _snapshot: snapshot,
        _events: events,
        _cellOutputs: _pollCellOutputs,
      };
      if (completedCellCount > 0 && totalCells > 0) {
        progressState.cellProgress = completedCellCount + "/" + totalCells;
      }
      if (actions && actions.setRunState) {
        actions.setRunState(progressState);
      }
    } else if (status === "completed" || status === "succeeded" || status === "cancelled" || status === "stopped") {
      // Terminal success/cancelled/stopped state.  When evidence exists
      // (completed cells or a terminal event in the journal), extract
      // outputs and mark completed with full snapshot/events/cellOutputs
      // so the grid viewport renders partial results after cancellation.
      if (hasCellCompletionEvidence || hasTerminalEvent) {
        _stopPolling(state);
        // Extract output evidence from cell.completed events
        const outputEvents = events.filter(function (ev) {
          return ev.type === "cell.completed" && ev.payload;
        });
        let primaryOutput = null;
        for (const ev of outputEvents) {
          const payload = ev.payload || {};
          if (payload.primary_asset_id) {
            primaryOutput = apiBase + "/assets/" + encodeURIComponent(payload.primary_asset_id);
            break;
          }
          if (payload.output_paths && payload.output_paths.length > 0) {
            const outputFilename = payload.output_paths[0];
            primaryOutput = apiBase + "/studio/outputs/" + encodeURIComponent(outputFilename);
            break;
          }
        }
        if (actions && actions.setRunState) {
          actions.setRunState({
            status: "completed",
            experimentId: experimentId,
            completedCells: completedCellCount || cellCompletedEvents,
            totalCells: totalCells,
            primaryOutput: primaryOutput,
            hasHistory: true,
            _snapshot: snapshot,
            _events: events,
            _cellOutputs: _pollCellOutputs,
          });
        }
      } else if (status === "completed" || status === "succeeded") {
        // Completed but no evidence yet — stay in current state,
        // bounded by the 5-minute POLL_TIMEOUT_MS above.
        // (Existing behavior: snapshot may be populated on next poll.)
      } else {
        // cancelled/stopped without evidence — still a terminal event.
        // Stop polling and show as completed with no cell data so the
        // grid does not hang indefinitely.
        _stopPolling(state);
        if (actions && actions.setRunState) {
          actions.setRunState({
            status: "completed",
            experimentId: experimentId,
            completedCells: 0,
            totalCells: totalCells || 0,
            message: "Run was " + status + " before any cells completed.",
            hasHistory: false,
            _snapshot: snapshot,
            _events: events,
            _cellOutputs: _pollCellOutputs,
          });
        }
      }
    } else if (status === "failed_fatal" || status === "error" || status === "failed" || status === "completed_with_failures") {
      _stopPolling(state);
      const errMsg = (lastErrorMsg || snapshot.error || data.message || data.error || "Run failed.").substring(0, 200);
      if (actions && actions.setRunState) {
        actions.setRunState({
          status: "error",
          message: errMsg,
          experimentId: experimentId,
        });
      }
    } else if (status === "draft" || !status) {
      // Safety net: if there are explicit error events even while status
      // shows draft/unknown, surface the error terminal state
      if (hasExplicitErrorEvent) {
        _stopPolling(state);
        const errMsg = (lastErrorMsg || "Run failed.").substring(0, 200);
        if (actions && actions.setRunState) {
          actions.setRunState({
            status: "error",
            message: errMsg,
            experimentId: experimentId,
          });
        }
      } else {
        // Still being set up — stay in waiting
        if (actions && actions.setRunState) {
          actions.setRunState({ status: "waiting", experimentId });
        }
      }
    }
  }, POLL_INTERVAL_MS);
  // Store timer reference on state (survives re-renders) instead of
  // container (destroyed on re-render from context.setPage calls).
  if (state && state.playground) state.playground._pollTimer = pollTimer;
}

// ── Effective Controls builder ────────────────────────────────────────────
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

  // A persisted draft contains explicit user edits — load into
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
 * Safe to call on every render — performs a synchronous localStorage write.
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

// ── Recent runs state management ──────────────────────────────────────────
//
// Reusable loader/state-owned collection of recent runs, refreshed:
//   - on initial hydration
//   - after finalized completion
//   - after preset deletion if needed
//   - when returning to Playground after History changes

let _recentRunsCache = null;
let _recentRunsCacheKey = "";

export async function refreshRecentRuns(apiBase) {
  try {
    // Fetch ordinary runs AND true Studio aggregate experiments in parallel
    var [runResp, expResp, unifiedResp] = await Promise.all([
      fetch(apiBase + "/run-history?limit=50"),
      fetch(apiBase + "/experiments"),
      fetch(apiBase + "/history?page=1&page_size=50"),
    ]);

    // ── Process ordinary runs ───────────────────────────────────────────
    var normalRuns = [];
    if (runResp && runResp.ok) {
      var data = await runResp.json();
      var entries = (data && data.runs) || [];
      if (unifiedResp && unifiedResp.ok) {
        var unifiedData = await unifiedResp.json();
        entries = entries.concat((unifiedData && unifiedData.items) || []);
      }
      // Filter to Studio runs
      var studioRuns = entries.filter(function (r) {
        var extra = (r && r.extra) || {};
        var studioMeta = extra.studio_meta || extra.studio_metadata || {};
        return (r.prompt_id && r.prompt_id.indexOf("studio_") === 0) ||
               r.kind === "experiment_cell" ||
               !!(extra.studio_feature_id || extra.studio_preset_id || studioMeta.studio_feature_id || studioMeta.studio_preset_id);
      });
      // Normalize and only keep completed/image-producing runs
      normalRuns = studioRuns.map(function (r) {
        return normalizeStudioRun(r, apiBase);
      }).filter(function (nr) {
        return nr
          && (nr.status === "completed" || nr.status === "success" || nr.status === "done")
          && (nr.imageUrl || nr.experimentId);
      });
    }

    // ── Process true Studio aggregate experiments ───────────────────────
    var experimentItems = [];
    if (expResp && expResp.ok) {
      var expData = await expResp.json();
      var experiments = (expData && expData.experiments) || [];
      experimentItems = experiments
        .filter(function (e) {
          // Only true Studio aggregate experiments:
          // definition name prefix "Studio Experiment:" AND studio_meta AND total_cells > 1
          var def = e.definition || {};
          var snap = e.snapshot || {};
          var studioMeta = def.studio_meta || {};
          var isStudioExp = (typeof def.name === "string" && def.name.indexOf("Studio Experiment:") === 0);
          var hasPresets = !!(studioMeta.studio_preset_ids && studioMeta.studio_preset_ids.length > 0);
          var multiCell = snap.total_cells > 1;
          return isStudioExp && hasPresets && multiCell;
        })
        .map(function (e) {
          var def = e.definition || {};
          var snap = e.snapshot || {};
          var studioMeta = def.studio_meta || {};
          var presetIds = studioMeta.studio_preset_ids || [];
          var expId = e.experiment_id || "";
          var counters = snap.counters || {};
          return {
            kind: "studio_experiment",
            experimentId: expId,
            id: expId,
            prompt: def.name || "Studio Experiment",
            promptId: "studio_" + expId,
            presetId: presetIds[0] || "",
            presetLabel: null,
            featureId: "txt2img",
            status: snap.overall_status || snap.status || "completed",
            imageUrl: null,
            startedAt: def.created_at || def.createdAt || snap.created_at || "",
            completedAt: snap.updated_at || snap.updatedAt || "",
            durationMs: null,
            favorite: false,
            _experimentData: e,
          };
        });
    }

    // ── Merge and sort by created time (newest first) ───────────────────
    var merged = normalRuns.concat(experimentItems);
    merged.sort(function (a, b) {
      var aTime = a.completedAt || a.startedAt || "";
      var bTime = b.completedAt || b.startedAt || "";
      return bTime.localeCompare(aTime);
    });

    // Deduplicate by ID (first occurrence of each key wins — newest)
    var seen = {};
    _recentRunsCache = merged.filter(function (item) {
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

// ── Hydration helper ──────────────────────────────────────────────────────
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
    // Invalid/deleted preset — try another runnable preset first
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
        return nr.presetId === targetPresetId && nr.featureId === featureId;
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
}

// ── Main Playground renderer ─────────────────────────────────────────────

export function renderPlayground(state, context) {
  const container = el("div", { class: "comfymodal-studio-playground" });

  // ── Scoped tracker lifecycle ────────────────────────────────────────
  // Studio progress is driven by a scoped tracker (per-run), NOT the
  // global shared tracker. This prevents unrelated ComfyUI executions
  // from driving the Studio progress UI.
  //
  // Scoped trackers are created in doRunSubmit (single runs) and in the
  // experiment run handlers, then disposed on terminal states.
  // The _scopedTracker reference in state.playground is managed there.
  //
  // Not subscribed for progress UI updates — only scoped trackers drive
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

// ── Left Control Panel (preset-driven) ──────────────────────────────────

function renderControlPanel(state, context) {
  const panel = el("div", { class: "comfymodal-studio-control-panel", "data-testid": "control-panel" });

  const isExperiment = state.playground && state.playground.experimentMode;
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const currentSpec = FEATURE_SPECS.find((f) => f.id === currentFeatureId) || FEATURE_SPECS[0];

  // Actions for state mutations (called by event handlers)
  const actions = buildActions(state, context);
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

    // Running config panel — sits directly below the experiment controls so
    // it remains visible even when the experiment grid replaces the normal
    // workspace content.  Shows frozen parameter values during active runs.
    panel.appendChild(renderRunningConfigPanel(state));
  }

  // ── Backend Selector ───────────────────────────────────────────────
  panel.appendChild(renderControlGroup("Backend", renderBackendSelector(state, actions, context)));

  // ── Preset-driven Controls ─────────────────────────────────────────
  const controlsContainer = el("div", { class: "comfymodal-studio-controls", "data-testid": "controls-container" });
  controlsContainer.appendChild(el("p", {
    text: "Loading preset capabilities...",
    style: "font-size:11px;color:#888;padding:8px;",
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
      // No preset selected — prompt to select one
      const noPresetMsg = el("div", {
        class: "comfymodal-studio-card",
        style: "padding:12px;text-align:center;",
      }, [
        el("p", {
          text: "Select a Backend Preset to see controls.",
          style: "font-size:11px;color:#888;margin:0 0 8px;",
        }),
        el("a", {
          text: "Go to Backend tab to create presets",
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

  // ── Run Button ─────────────────────────────────────────────────────
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

// ── Actions builder ──────────────────────────────────────────────────────

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
      // Dispose scoped tracker — switching features invalidates current run
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
      // Dispose scoped tracker — switching backends invalidates current run
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
        // Persist experiment draft — prompt-axis first value changed
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
        && (currentRunState.status === "completed" || currentRunState.status === "error");
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
      // Persist experiment draft — axes toggles are a persistence trigger
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
      // Persist experiment draft — axis values changed
      _saveExperimentDraftFromState(state);
      // Re-render when value count changes (add/remove), but NOT on every
      // keystroke — that would thrash the UI during text input.
      if (values.length !== prevLen && context && context.setPage) {
        context.setPage("playground");
      }
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
      const prevRunState = state.playground.runState;
      const prevStatus = prevRunState && prevRunState.status;
      state.playground.runState = { ...state.playground.runState, ...runState };

      const newStatus = runState && runState.status;

      // Dispose scoped tracker and clean up local timer on terminal states
      if (runState && (newStatus === "completed" || newStatus === "error")) {
        if (state.playground && state.playground.runState) {
          delete state.playground.runState._localStartTime;
          delete state.playground.runState._cancelling;
        }
        // Clean up captured running config — a new run will re-capture
        if (state.playground) delete state.playground._runningExperimentConfig;
        _disposeScopedTracker(state);
      }

      if (runState && newStatus === "completed") {
        // A new run completed — re-enable the carousel synchronously so
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
            // Find the matching run by experiment ID
            matched = runs.find(function (nr) {
              return nr.experimentId === experimentId;
            });
            if (!matched) {
              // Fallback: find by preset+feature
              matched = runs.find(function (nr) {
                return nr.presetId === state.playground.selectedBackendId &&
                       nr.featureId === (state.playground.featureId || "txt2img");
              });
            }
          }
          if (matched) {
            state.playground._selectedRun = matched;
            // Never nullify lastRunOutput — primaryOutput has already been set.
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
        // Clearing runState — preserve lastRunOutput and _selectedRun so
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
    if (!select.isConnected) return;
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

  // ── Schema-kind dispatch (backend truth) ─────────────────────────────
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
    // Preserve falsy zero/false — only truly missing treated as default
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

  // ── Static CONTROL_DEFS type dispatch (fallback) ─────────────────────
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
          text: "Configure in Legacy Setup",
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

  // ── Steps: Use Recommended (N) button ──────────────────────────────
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

// ── Run Button ───────────────────────────────────────────────────────────

// ── Single-run submit helper ──────────────────────────────────────────────
//
// Immediately submits a single run using visible controls.
// Deduplicated from the inline handler in renderRunButton so that
// completed/error state can re-submit in a single click.

function _disposeScopedTracker(state) {
  // Note: does NOT clean _localElapsedTimer — the local timer is owned by
  // _startLocalElapsedTimer which handles cleanup and re-creation across
  // new-run boundaries. Terminal cleanup is done by setRunState.

  var st = state.playground && state.playground._scopedTracker;
  if (st && typeof st.dispose === "function") {
    try { st.dispose(); } catch {}
  }
  if (state.playground) state.playground._scopedTracker = null;
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
    if (_rs2.status === "completed" || _rs2.status === "error") {
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
    // DOM-targeted elapsed update — avoids full page teardown on every tick
    var elapsedEl = document.querySelector('[data-testid="progress-elapsed"]');
    if (elapsedEl) {
      elapsedEl.textContent = "Elapsed: " + _formatDuration(_rs2.elapsedMs);
    }
  }, 250);

  if (state.playground) state.playground._localElapsedTimer = _timer;
}

function _createAndStartScopedTracker(state, context, runId, experimentId) {
  // Dispose any existing scoped tracker first
  _disposeScopedTracker(state);

  var api = (context && context.comfyApi) || (context && context.api);
  // If no api available, cannot create scoped tracker — polling will handle progress
  if (!api || typeof api.addEventListener !== "function") return null;

  var tracker = createScopedTracker(api, { runId: runId, experimentId: experimentId, promptId: null });
  state.playground._scopedTracker = tracker;

  // Subscribe tracker updates to runState
  tracker.onProgress(function (s) {
    var rs = state.playground.runState || {};
    // Scoped tracker only produces updates for OUR run — no isInFlight guard needed
    if (!rs.status) return;

    // Map tracker stage to runState status
    var mappedStatus = rs.status;
    if (s.stage === "startup") mappedStatus = "in_progress";
    else if (s.stage === "generating") mappedStatus = "in_progress";
    else if (s.stage === "done") mappedStatus = "completed";
    else if (s.stage === "error") mappedStatus = "error";
    else if (s.stage === "idle" && rs.status !== "submitted") return;

    // Always apply tracker snapshot fields to runState (no guard — prevents
    // stale display after status stabilizes to "in_progress")
    rs.overallPercent = s.overallPercent;
    rs.completedNodes = s.completedNodes;
    rs.totalNodes = s.totalNodes;
    rs.samplerStep = s.samplerStep;
    rs.samplerMaximum = s.samplerMaximum;
    rs.samplerPercent = s.samplerPercent;
    // elapsedMs is handled by local timer (preserves original press timestamp)
    rs.queuePosition = s.queuePosition;
    rs.currentNodeLabel = s.currentNodeLabel;
    rs.stage = s.stage;
    rs.message = s.message;
    rs.error = s.error;

    var statusChanged = mappedStatus !== rs.status;
    if (statusChanged) {
      rs.status = mappedStatus;
    }

    // Trigger re-render on terminal states (dispose tracker) or meaningful
    // status transitions.  Intermediate progress uses DOM-targeted patching
    // to avoid 4-8Hz full page teardown.
    if (mappedStatus === "completed" || mappedStatus === "error") {
      // Dispose scoped tracker on terminal state
      delete rs._localStartTime;
      _disposeScopedTracker(state);
      if (context && context.setPage) context.setPage("playground");
    } else if (statusChanged) {
      // Meaningful status transition (submitted→in_progress, etc.) — full rerender
      if (context && context.setPage) context.setPage("playground");
    } else {
      // Intermediate progress: DOM-targeted patch, no full re-render
      _domPatchProgress(state);
    }
  });

  tracker.start();
  return tracker;
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
 * Handle a direct-run completed result — no polling or journal needed.
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

  // Dispose scoped tracker — no polling needed for direct run
  _disposeScopedTracker(state);

  if (actions && actions.setRunState) {
    actions.setRunState({
      status: "completed",
      runId: result.runId || result.runHistoryId || result.experimentId || "",
      experimentId: result.experimentId || result.runId || "",
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

async function doRunSubmit(state, context, actions) {
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

  const apiBase = (context && context.apiBase) || "/comfymodal";
  const currentFeatureId = (state.playground && state.playground.featureId) || "txt2img";
  const selectedId = state.playground && state.playground.selectedBackendId;
  if (!selectedId) return;

  const { listPresets } = await import("./studio-backend-api.js");
  const presets = await listPresets(apiBase) || [];
  const preset = presets.find(function (p) { return (p.id || p.label || "") === selectedId; });
  if (!preset) return;

  const controls = buildEffectiveControls(state, preset, currentFeatureId);

  const validationError = validateControls(controls, preset);
  if (validationError) {
    if (actions && actions.setRunState) {
      actions.setRunState({ status: "error", message: validationError });
    }
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
  if (actions && actions.setRunState) {
    actions.setRunState({ status: "running", samplerStep: 0, samplerMaximum: _runMaxSteps });
  }
  // Start local elapsed timer immediately on press
  _startLocalElapsedTimer(state, context);

  // Capture client-side timestamps at press time (top-level `trace` for server)
  const t0_perf_ms = performance.now();
  const t0_now = Date.now();

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

  if (result && result.status === "ok") {
    // ── Direct run: result is already completed, no polling ──────────
    if (_handleDirectRunResult(result, state, context, actions, controls)) {
      return;
    }

    // ── Scheduler path: result is a submission, start polling ───────
    // Dispose any previous scoped tracker before creating new one
    _disposeScopedTracker(state);

    // Derive initial sampler maximum from submitted steps control
    var _submittedSteps = controls.steps;
    var _initialSamplerMax = (_submittedSteps != null && Number(_submittedSteps) > 0) ? Number(_submittedSteps) : 0;

    if (actions && actions.setRunState) {
      actions.setRunState({
        status: "submitted",
        runId: result.runId || result.experimentId,
        experimentId: result.experimentId,
        samplerStep: 0,
        samplerMaximum: _initialSamplerMax,
      });
    }

    // Restart local elapsed timer after dispose; preserves original _localStartTime
    _startLocalElapsedTimer(state, context);

    // Create scoped tracker for this run's execution events
    _createAndStartScopedTracker(
      state, context,
      result.runId || result.experimentId,
      result.experimentId
    );
  } else {
    const errMsg = (result && result.message) || "Run failed.";
    if (result && result.error_code) {
      console.error("[Studio run] execution failed", {
        error_code: result.error_code,
        error: result.error || null,
      });
    }
    if (actions && actions.setRunState) {
      actions.setRunState({ status: "error", message: errMsg });
    }
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
      doRunSubmit(state, context, actions);
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
      doRunSubmit(state, context, actions);
    };
    return container;
  }

  // Async-load presets to determine runnability
  getRuntimePresets({ apiBase }).then((presets) => {
    if (!container.isConnected) return;
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

    // ── Single run mode (also used in experiment mode, since experiment
    //     mode has its own dedicated "Run Experiment" button) ──────────
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

        // Build controls early so sampler fields are available for running state
        const controls = buildEffectiveControls(state);

        // Clear previous output so canvas shows live progress immediately
        state.playground.lastRunOutput = null;
        state.playground._selectedRun = null;

        // Put determinate sampler fields into running state BEFORE remote call
        var _runSteps = controls.steps;
        var _runMaxSteps = (_runSteps != null && Number(_runSteps) > 0) ? Number(_runSteps) : 0;
        if (actions && actions.setRunState) actions.setRunState({ status: "running", samplerStep: 0, samplerMaximum: _runMaxSteps });
        // Start local elapsed timer immediately on press
        _startLocalElapsedTimer(state, context);

        const validationError = validateControls(controls, preset);
        if (validationError) {
          btn.disabled = false;
          btn.textContent = "Run";
          if (actions && actions.setRunState) {
            actions.setRunState({ status: "error", message: validationError });
          }
          return;
        }
        const modalOptions = await buildStudioModalOptions(apiBase);

        // Capture client-side timestamps at press time (top-level `trace` for server)
        var t0_perf_ms = performance.now();
        var t0_now = Date.now();

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

        if (result && result.status === "ok") {
          // ── Direct run: result is already completed, no polling ──
          if (_handleDirectRunResult(result, state, context, actions, controls)) {
            return;
          }

          // ── Scheduler path: submission, start polling ────────────
          // Dispose any previous scoped tracker before creating new one
          _disposeScopedTracker(state);

          // Derive initial sampler maximum from submitted steps control
          var _inlineSteps = controls.steps;
          var _inlineSamplerMax = (_inlineSteps != null && Number(_inlineSteps) > 0) ? Number(_inlineSteps) : 0;

          if (actions && actions.setRunState) {
            actions.setRunState({
              status: "submitted",
              runId: result.runId || result.experimentId,
              experimentId: result.experimentId,
              samplerStep: 0,
              samplerMaximum: _inlineSamplerMax,
            });
          }

          // Restart local elapsed timer after dispose; preserves original _localStartTime
          _startLocalElapsedTimer(state, context);

          // Create scoped tracker for this run's execution events
          _createAndStartScopedTracker(
            state, context,
            result.runId || result.experimentId,
            result.experimentId
          );
        } else {
          const errMsg = (result && result.message) || "Run failed.";
          if (actions && actions.setRunState) {
            actions.setRunState({ status: "error", message: errMsg });
          }
        }
      };
    }
  }).catch(() => {
    if (!container.isConnected) return;
    while (reason.firstChild) reason.removeChild(reason.firstChild);
    reason.appendChild(el("p", {
      text: "Could not load presets.",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    }));
  });

  return container;
}

// ── Progress Section ─────────────────────────────────────────────────────
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
  if (!runState || runState.status === "completed" || runState.status === "error") {
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

// ── Running Config Panel ────────────────────────────────────────────────
//
// Displays the parameter values that were captured at experiment submit
// time, so the user can see what's being run even after editing form
// controls.  Only renders when state.playground._runningExperimentConfig
// is set (experiment-mode submissions via buildExperimentClickHandler).
// Shows prompt, CFG, steps, seed, sampler, scheduler, denoise, dimensions,
// experiment axes, and preset info.

function renderRunningConfigPanel(state) {
  const panel = el("div", {
    class: "comfymodal-studio-running-config",
    "data-testid": "running-config-panel",
  });

  const config = state.playground && state.playground._runningExperimentConfig;
  const runState = state.playground && state.playground.runState;

  // Only show during active runs with a captured config snapshot
  if (!config || !runState) return panel;
  var rs = runState.status;
  var isActive = rs && rs !== "completed" && rs !== "error" && rs !== "idle";
  if (!isActive) return panel;
  panel.classList.add("is-visible");

  var controls = config.controls || {};
  var axes = config.axes || {};

  // ── Header ────────────────────────────────────────────────────────
  var headerChildren = [
    el("span", { class: "comfymodal-studio-running-config-title", text: "Run Config" }),
  ];
  if (config.presetLabel) {
    headerChildren.push(el("span", {
      class: "comfymodal-studio-running-config-preset",
      text: config.presetLabel,
    }));
  }
  panel.appendChild(el("div", { class: "comfymodal-studio-running-config-header" }, headerChildren));

  // ── Prompt (skip if it's an experiment axis — axes section shows values) ──
  var promptIsAxis = axes.prompt && axes.prompt.enabled;
  if (!promptIsAxis && controls.prompt != null && controls.prompt !== "") {
    panel.appendChild(el("div", { class: "comfymodal-studio-running-config-prompt" }, [
      el("span", { class: "comfymodal-studio-running-config-label", text: "Prompt" }),
      el("span", { class: "comfymodal-studio-running-config-prompt-text", text: controls.prompt }),
    ]));
  }

  // ── Negative prompt (skip if it's an experiment axis) ─────────────
  var negIsAxis = axes.negative_prompt && axes.negative_prompt.enabled;
  if (!negIsAxis && controls.negative_prompt != null && controls.negative_prompt !== "") {
    panel.appendChild(el("div", { class: "comfymodal-studio-running-config-prompt", style: "border-bottom:none;margin-bottom:2px;padding-bottom:2px;" }, [
      el("span", { class: "comfymodal-studio-running-config-label", text: "Negative" }),
      el("span", { class: "comfymodal-studio-running-config-prompt-text", text: controls.negative_prompt }),
    ]));
  }

  // ── Parameter grid ────────────────────────────────────────────────
  var paramKeys = ["guidance", "steps", "seed", "sampler", "scheduler", "denoise", "width", "height"];
  var paramEntries = [];
  paramKeys.forEach(function (key) {
    if (controls[key] != null && controls[key] !== "") {
      var def = CONTROL_DEFS[key];
      var label = def ? def.label : key;
      paramEntries.push({ label: label, value: String(controls[key]) });
    }
  });

  if (paramEntries.length > 0) {
    var grid = el("div", { class: "comfymodal-studio-running-config-grid" });
    paramEntries.forEach(function (entry) {
      grid.appendChild(el("span", { class: "comfymodal-studio-running-config-item" }, [
        el("span", { class: "comfymodal-studio-running-config-label", text: entry.label + ": " }),
        el("span", { class: "comfymodal-studio-running-config-value", text: entry.value }),
      ]));
    });
    panel.appendChild(grid);
  }

  // ── Experiment axes ───────────────────────────────────────────────
  var activeAxes = [];
  for (var _ctrlId in axes) {
    if (Object.prototype.hasOwnProperty.call(axes, _ctrlId)) {
      var _adef = axes[_ctrlId];
      if (_adef && _adef.enabled && _adef.values && _adef.values.length > 0) {
        activeAxes.push([_ctrlId, _adef]);
      }
    }
  }

  if (activeAxes.length > 0) {
    var axesSection = el("div", { class: "comfymodal-studio-running-config-axes" }, [
      el("span", { class: "comfymodal-studio-running-config-axes-title", text: "Experiment Axes" }),
    ]);
    var axesList = el("div", { class: "comfymodal-studio-running-config-axes-list" });
    activeAxes.forEach(function (pair) {
      var _id = pair[0];
      var _def = pair[1];
      var _ctrlDef = CONTROL_DEFS[_id] || {};
      var _label = _ctrlDef.label || _id;
      var _vals = (_def.values || []).map(String).join(", ");
      axesList.appendChild(el("span", {
        class: "comfymodal-studio-running-config-axis-item",
        text: _label + ": " + _vals,
      }));
    });
    axesSection.appendChild(axesList);
    panel.appendChild(axesSection);
  }

  // ── Preset count (multi-preset experiments) ────────────────────────
  var presetIds = config.presetIds || [];
  if (presetIds.length > 1) {
    panel.appendChild(el("div", {
      class: "comfymodal-studio-running-config-preset-count",
      text: presetIds.length + " preset" + (presetIds.length > 1 ? "s" : ""),
    }));
  }

  return panel;
}

// ── Experiment Grid Viewport ─────────────────────────────────────────────
//
// Renders the experiment results grid in the workspace when experiment mode
// is active and snapshot data is available.  Replaces the normal single-run
// canvas/progress/metadata/filmstrip sections.
//
// Layout adapts to the number of varying axes:
//   0 axes → checkpoint-based groups (fallback)
//   1 axis → horizontal row with axis-value headers
//   2 axes → 2D matrix with row/column axis-value headers
//   3-4 axes → 2D matrix (first 2 axes as axes) with remaining axes in cell labels
//
// During active runs, pending cells show clickable placeholders and the
// currently-running cell shows an animated loading indicator.  Two progress
// bars at bottom: current cell sampler progress + overall cell completion.
//
// After completion, output thumbnails appear in their correct grid cells.
// Clicking any cell opens a detail overlay showing axis values (in red).

export function _buildCellOutputMap(events, apiBase) {
  var map = {};
  if (!events) return map;
  events.forEach(function (ev) {
    if (ev.type === "cell.completed" && ev.payload) {
      var ck = ev.payload.cell_key;
      if (!ck) return;
      var url = null;
      if (ev.payload.primary_asset_id) {
        url = apiBase + "/assets/" + encodeURIComponent(ev.payload.primary_asset_id);
      } else if (ev.payload.output_paths && ev.payload.output_paths.length > 0) {
        url = apiBase + "/studio/outputs/" + encodeURIComponent(ev.payload.output_paths[0]);
      }
      if (url) map[ck] = url;
    }
  });
  return map;
}

// ── Experiment Loader (exported for History reuse) ─────────────────────────
//
// Fetches experiment detail via getStudioRunStatus and populates state so
// the Experiment Grid viewport renders in the Playground.  On error returns
// { ok: false, error: string } without navigating.

export async function loadExperimentIntoPlayground(state, context, experimentId) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const data = await getStudioRunStatus(apiBase, experimentId);
    if (!data) {
      return { ok: false, error: "No response from server." };
    }
    if (data.status && data.status !== "ok") {
      return { ok: false, error: (data.message || data.error || "Failed to load experiment.").substring(0, 200) };
    }
    if (!data.snapshot) {
      return { ok: false, error: "Experiment has no snapshot data yet." };
    }
    const snapshot = data.snapshot || {};
    const events = data.events || [];
    const cellOutputs = _buildCellOutputMap(events, apiBase);
    const snapStatus = snapshot.overall_status || snapshot.status || "completed";

    if (!state.playground) state.playground = {};
    state.playground.experimentMode = true;
    state.playground.runState = {
      status: snapStatus,
      experimentId: experimentId,
      _snapshot: snapshot,
      _events: events,
      _cellOutputs: cellOutputs,
    };

    if (context && context.setPage) {
      context.setPage("playground");
    }
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message || "Failed to load experiment." };
  }
}

function renderExperimentGridViewport(state, context) {
  const viewport = el("div", {
    class: "comfymodal-studio-experiment-grid-viewport",
    "data-testid": "experiment-grid-viewport",
  });

  const runState = state.playground && state.playground.runState;
  const snapshot = runState && runState._snapshot;
  const events = runState && runState._events;
  const cellOutputs = runState && runState._cellOutputs;
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // If experiment run is active but no snapshot yet, show building state
  if (!snapshot) {
    viewport.appendChild(el("div", {
      class: "comfymodal-studio-experiment-grid-building",
      "data-testid": "experiment-grid-building",
      text: "Assembling experiment cells\u2026",
    }));
    return viewport;
  }

  // Extract compilation cells from experiment.created event
  var compilationCells = _getCompilationCells(events);
  if (!compilationCells || compilationCells.length === 0) {
    // Fall back to snapshot cell_visible keys if compilation not available
    var cellVisible = snapshot.cell_visible;
    if (cellVisible && typeof cellVisible === "object") {
      var vKeys = Object.keys(cellVisible);
      if (vKeys.length > 0) {
        compilationCells = vKeys.map(function (ck) {
          return { cell_key: ck, axis_values: {} };
        });
      }
    }
  }
  if (!compilationCells || compilationCells.length === 0) {
    // Last resort: synthesize cells from cell.completed / cell.failed events
    var synthesized = _synthesizeCellsFromEvents(events);
    if (synthesized && synthesized.length > 0) {
      compilationCells = synthesized;
    }
  }
  if (!compilationCells || compilationCells.length === 0) {
    // Fallback to total_cells count from snapshot
    var totalExpected = snapshot.total_cells || 0;
    if (totalExpected > 0) {
      compilationCells = [];
      for (var ci = 0; ci < totalExpected; ci++) {
        compilationCells.push({ cell_key: "cell_" + ci, axis_values: {} });
      }
    }
  }
  if (!compilationCells || compilationCells.length === 0) {
    viewport.appendChild(el("div", {
      class: "comfymodal-studio-experiment-grid-building",
      "data-testid": "experiment-grid-building",
      text: "No cell data available yet\u2026",
    }));
    return viewport;
  }

  // Merge compilation cells with snapshot + event data + output URLs
  var entries = _mergeCellStateForGrid(compilationCells, events, snapshot, cellOutputs, apiBase);

  // Determine varying axes for layout
  var axisInfo = _computeGridAxes(entries);
  var varyingAxes = axisInfo.axes;

  // Grid container (scrollable)
  var gridOuter = el("div", { class: "comfymodal-studio-experiment-grid-outer", "data-testid": "experiment-grid-outer" });

  // Axis-count-based layout dispatch
  if (varyingAxes.length === 0) {
    _renderGridFallback(gridOuter, entries, apiBase, state, context, snapshot);
  } else if (varyingAxes.length === 1) {
    _renderGridLinear(gridOuter, entries, varyingAxes, apiBase, state, context, snapshot);
  } else {
    _renderGridMatrix(gridOuter, entries, varyingAxes, apiBase, state, context, snapshot);
  }

  viewport.appendChild(gridOuter);

  // Two progress bars at bottom
  viewport.appendChild(_renderExperimentProgressBars(runState, state));

  // Total time display (always rendered, uses — placeholder when unavailable)
  var totalTimeRow = el("div", {
    class: "comfymodal-studio-experiment-grid-progress-row",
    "data-testid": "experiment-total-time",
    style: "margin-top:4px;padding-top:4px;border-top:1px solid #222;",
  });
  totalTimeRow.appendChild(el("span", {
    class: "comfymodal-studio-experiment-grid-progress-label",
    text: "Total time",
  }));
  totalTimeRow.appendChild(el("span", {
    style: "font-size:10px;color:#aaa;margin-left:auto;font-variant-numeric:tabular-nums;",
    "data-testid": "experiment-total-time-value",
    text: _formatTotalExperimentTime(runState, snapshot, events, entries),
  }));
  viewport.appendChild(totalTimeRow);

  // Cell detail overlay (shown when _selectedCellKey is set)
  var selectedCellKey = state.playground && state.playground._selectedCellKey;
  if (selectedCellKey) {
    var detailEntry = null;
    for (var i = 0; i < entries.length; i++) {
      if (entries[i].cell.cell_key === selectedCellKey) {
        detailEntry = entries[i];
        break;
      }
    }
    if (detailEntry) {
      viewport.appendChild(_renderCellDetailOverlay(detailEntry, entries, apiBase, state, context, varyingAxes));
    }
  }

  // Enable spatial arrow navigation after the grid has rendered
  // Schedule after browser paint so all elements have their final positions
  setTimeout(function () {
    var cleanup = _enableGridArrowNavigation(viewport);
    // Store cleanup on viewport for future cleanup if needed
    viewport._arrowNavCleanup = cleanup;
  }, 0);

  return viewport;
}

/**
 * Compute total experiment wall-clock time using prioritized sources:
 *   1. Snapshot-level total_duration_ms (explicit field)
 *   2. Experiment definition timestamps (completed_at - created_at)
 *   3. Cell-duration sum (fallback)
 *   4. Live elapsed when active (non-terminal)
 * Returns formatted string or placeholder dash.
 */
function _formatTotalExperimentTime(runState, snapshot, events, entries) {
  // ── Priority 1: explicit total_duration_ms on snapshot ──
  if (snapshot && snapshot.total_duration_ms != null) {
    var td = Number(snapshot.total_duration_ms);
    if (!isNaN(td) && td > 0) return _formatDuration(td);
  }

  // ── Priority 2: wall-clock from event timestamps ──
  if (events && events.length >= 2) {
    var startEv = null;
    var endEv = null;
    for (var _ei = 0; _ei < events.length; _ei++) {
      var t = events[_ei].type;
      if (t === "experiment.started" || t === "experiment.created") {
        startEv = events[_ei];
      } else if (t === "experiment.completed" || t === "experiment.failed_fatal" || t === "experiment.stopped") {
        endEv = events[_ei];
      }
    }
    // Check for timestamp at event level, then created_at at payload or event level
    var startTs = startEv && (startEv.timestamp || startEv.created_at || (startEv.payload && startEv.payload.created_at));
    var endTs = endEv && (endEv.timestamp || endEv.created_at || (endEv.payload && endEv.payload.created_at));
    if (startTs && endTs) {
      var s = new Date(startTs).getTime();
      var e = new Date(endTs).getTime();
      if (!isNaN(s) && !isNaN(e) && e > s) return _formatDuration(e - s);
    }
  }

  // ── Priority 3: live elapsed when active ──
  var isTerminal = runState.status === "completed" || runState.status === "error";
  if (runState.elapsedMs != null && !isTerminal) {
    var el = Number(runState.elapsedMs);
    if (!isNaN(el) && el > 0) return _formatDuration(el);
  }

  // ── Priority 4: cell-duration sum (fallback) ──
  var sumMs = 0;
  var hasAnyDuration = false;
  for (var _si = 0; _si < entries.length; _si++) {
    var dur = _getCellDuration(entries[_si].attempt);
    if (dur != null && dur > 0) {
      sumMs += dur;
      hasAnyDuration = true;
    }
  }
  if (hasAnyDuration && sumMs > 0) return _formatDuration(sumMs);

  // ── No data available — visible placeholder ──
  return "\u2014";
}

function _getCompilationCells(events) {
  if (!events) return null;
  var createdEv = null;
  for (var i = 0; i < events.length; i++) {
    if (events[i].type === "experiment.created") {
      createdEv = events[i];
      break;
    }
  }
  if (!createdEv || !createdEv.payload) return null;
  var compilation = createdEv.payload.compilation;
  if (!compilation || !Array.isArray(compilation.cells)) return null;
  return compilation.cells;
}

function _synthesizeCellsFromEvents(events) {
  if (!events) return null;
  var seen = {};
  var cells = [];
  events.forEach(function (ev) {
    var ck = ev.payload && ev.payload.cell_key;
    if (!ck) return;
    if (seen[ck]) return;
    seen[ck] = true;
    cells.push({ cell_key: ck, axis_values: {} });
  });
  return cells.length > 0 ? cells : null;
}

function _mergeCellStateForGrid(compilationCells, events, snapshot, cellOutputs, apiBase) {
  // Build event-derived attempt map (latest event per cell_key wins)
  var eventAttempts = {};
  if (events) {
    events.forEach(function (ev) {
      var t = ev.type;
      var p = ev.payload || {};
      var ck = p.cell_key;
      if (!ck) return;
      if (t === "experiment.created") return;
      if (t === "cell.attempt_created") {
        eventAttempts[ck] = eventAttempts[ck] || {};
        eventAttempts[ck].attempt = Object.assign({}, p);
        eventAttempts[ck].attempt.status = "pending";
      } else if (["cell.completed", "cell.failed", "cell.interrupted", "cell.skipped"].indexOf(t) >= 0) {
        var status = t.split(".")[1];
        var prev = eventAttempts[ck] || {};
        eventAttempts[ck] = {
          cell: { cell_key: ck },
          attempt: Object.assign({}, prev.attempt || {}, p, { status: status }),
        };
      }
    });
  }
  // Merge compilation cells with event/snapshot/output data
  return compilationCells.map(function (compCell) {
    var ck = compCell.cell_key;
    var evData = eventAttempts[ck] || {};
    var snapAtt = (snapshot && snapshot.attempts && snapshot.attempts[ck]) || {};
    var visibleStatus = (snapshot && snapshot.cell_visible && snapshot.cell_visible[ck]) || null;
    var attempt = Object.assign({}, evData.attempt || {}, snapAtt);
    attempt.status = visibleStatus || snapAtt.status || (evData.attempt ? evData.attempt.status : null) || "pending";
    // Resolve output URL
    var outputUrl = null;
    if (cellOutputs && cellOutputs[ck]) {
      outputUrl = cellOutputs[ck];
    } else if (attempt.primary_asset_id) {
      outputUrl = apiBase + "/assets/" + encodeURIComponent(attempt.primary_asset_id);
    } else if (attempt.output_paths && attempt.output_paths.length > 0) {
      outputUrl = apiBase + "/studio/outputs/" + encodeURIComponent(attempt.output_paths[0]);
    }
    return {
      cell: Object.assign({ cell_key: ck, axis_values: compCell.axis_values || {} }, compCell),
      attempt: attempt,
      outputUrl: outputUrl,
    };
  });
}

function _computeGridAxes(entries) {
  if (!entries || entries.length === 0) return { axes: [] };
  var allValues = {};
  var firstSeenKeys = [];
  for (var i = 0; i < entries.length; i++) {
    var av = entries[i].cell.axis_values || {};
    for (var key in av) {
      if (!Object.prototype.hasOwnProperty.call(av, key)) continue;
      // Skip workflow-owned sentinel keys
      if (typeof key === "string" && key.indexOf("__") === 0) continue;
      if (!allValues[key]) {
        allValues[key] = new Set();
        firstSeenKeys.push(key);
      }
      var v = av[key];
      var sv = typeof v === "object" ? JSON.stringify(v) : String(v);
      // Skip workflow-owned sentinel values
      if (sv.indexOf("__COMFYMODAL_WORKFLOW_OWNED__") >= 0) continue;
      allValues[key].add(sv);
    }
  }
  // Detect varying prompts: compile cell.prompt values across entries
  var prompts = [];
  for (var pi = 0; pi < entries.length; pi++) {
    var pv = entries[pi].cell.prompt;
    if (pv != null && pv !== "") prompts.push(pv);
  }
  var promptsVary = false;
  if (prompts.length >= 2) {
    var firstP = prompts[0];
    for (var pj = 1; pj < prompts.length; pj++) {
      if (prompts[pj] !== firstP) { promptsVary = true; break; }
    }
  }
  var varying = [];
  for (var j = 0; j < firstSeenKeys.length; j++) {
    var k = firstSeenKeys[j];
    // Only include axes where the value Set has >1 distinct, non-sentinel entries
    if (allValues[k].size > 1) {
      varying.push(k);
    }
  }
  // If prompts vary, add "prompt" as a synthetic axis (takes priority after real axes)
  if (promptsVary) {
    varying.push("prompt");
  }
  return { axes: varying, valueSets: allValues };
}

function _getAxisValueLabel(entry, axisKey) {
  if (axisKey === "prompt") {
    // Synthetic prompt axis: value comes from cell.prompt not axis_values
    var p = entry.cell.prompt;
    if (p == null || p === "") return "(empty)";
    return String(p);
  }
  var av = entry.cell.axis_values || {};
  var v = av[axisKey];
  if (v === null || v === undefined) return "?";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function _renderGridFallback(gridOuter, entries, apiBase, state, context, snapshot) {
  // Group by checkpoint_id
  var groups = {};
  entries.forEach(function (entry) {
    var ck = (entry.attempt && entry.attempt.checkpoint_id) || "_unknown";
    groups[ck] = groups[ck] || [];
    groups[ck].push(entry);
  });
  var groupKeys = Object.keys(groups);
  var _cellIdx = 0;
  groupKeys.forEach(function (groupKey) {
    var group = el("div", { class: "comfymodal-studio-experiment-grid-group" }, [
      el("h4", {
        class: "comfymodal-studio-experiment-grid-group-label",
        text: "Checkpoint " + groupKey,
      }),
    ]);
    var row = el("div", { class: "comfymodal-studio-experiment-grid-row" });
    groups[groupKey].forEach(function (entry) {
      row.appendChild(_renderExperimentCell(entry, apiBase, state, context, _cellIdx));
      _cellIdx++;
    });
    group.appendChild(row);
    gridOuter.appendChild(group);
  });
  if (groupKeys.length === 0) {
    gridOuter.appendChild(el("div", {
      class: "comfymodal-studio-experiment-grid-empty",
      text: "No cells yet\u2026",
    }));
  }
}

function _renderGridLinear(gridOuter, entries, varyingAxes, apiBase, state, context, snapshot) {
  var axisKey = varyingAxes[0];
  // Collect unique values preserving compilation order
  var uniqueVals = [];
  var seen = {};
  entries.forEach(function (entry) {
    var val = _getAxisValueLabel(entry, axisKey);
    if (!seen.hasOwnProperty(val)) {
      seen[val] = true;
      uniqueVals.push(val);
    }
  });
  var container = el("div", { class: "comfymodal-studio-experiment-grid-container" });
  // Column headers
  var headerRow = el("div", { class: "comfymodal-studio-experiment-grid-row" });
  headerRow.appendChild(el("div", { class: "comfymodal-studio-experiment-grid-corner" }));
  var colHeaders = el("div", { class: "comfymodal-studio-experiment-grid-row-cells" });
  var isPromptAxis = axisKey === "prompt";
  uniqueVals.forEach(function (val) {
    var headerEl = el("div", {
      class: "comfymodal-studio-experiment-grid-header" + (isPromptAxis ? " is-prompt" : ""),
    });
    if (isPromptAxis) {
      headerEl.appendChild(el("span", {
        class: "comfymodal-studio-experiment-grid-header-prompt-text",
        text: val,
        title: val,
      }));
    } else {
      headerEl.textContent = val;
    }
    colHeaders.appendChild(headerEl);
  });
  headerRow.appendChild(colHeaders);
  container.appendChild(headerRow);
  // Cell row
  var cellRow = el("div", { class: "comfymodal-studio-experiment-grid-row" });
  cellRow.appendChild(el("div", { class: "comfymodal-studio-experiment-grid-corner" }));
  var cellRowCells = el("div", { class: "comfymodal-studio-experiment-grid-row-cells" });
  uniqueVals.forEach(function (val) {
    var match = null;
    var matchIdx = -1;
    for (var i = 0; i < entries.length; i++) {
      if (_getAxisValueLabel(entries[i], axisKey) === val) {
        match = entries[i];
        matchIdx = i;
        break;
      }
    }
    if (match) {
      // Augment entry with axis display info for cell detail
      match._axisLabels = match._axisLabels || {};
      match._axisLabels[axisKey] = val;
      cellRowCells.appendChild(_renderExperimentCell(match, apiBase, state, context, matchIdx));
    } else {
      cellRowCells.appendChild(_renderEmptyCell(axisKey + ": " + val));
    }
  });
  cellRow.appendChild(cellRowCells);
  container.appendChild(cellRow);
  gridOuter.appendChild(container);
}

function _renderGridMatrix(gridOuter, entries, varyingAxes, apiBase, state, context, snapshot) {
  var rowAxisKey = varyingAxes[0];
  var colAxisKey = varyingAxes[1];
  var extraAxes = varyingAxes.slice(2);
  // Collect unique values for row/col axes preserving order
  var rowVals = [];
  var colVals = [];
  var rowSeen = {}, colSeen = {};
  entries.forEach(function (entry) {
    var rv = _getAxisValueLabel(entry, rowAxisKey);
    var cv = _getAxisValueLabel(entry, colAxisKey);
    if (!rowSeen.hasOwnProperty(rv)) { rowSeen[rv] = true; rowVals.push(rv); }
    if (!colSeen.hasOwnProperty(cv)) { colSeen[cv] = true; colVals.push(cv); }
  });
  var container = el("div", { class: "comfymodal-studio-experiment-grid-container" });
  // Build multi-entry lookup: (rowVal, colVal) → [entry, ...]
  // For 3+ varying axes, multiple cells share the same row/col coordinates.
  // All cells at the same coordinate are stacked vertically in one grid cell.
  var lookup = {};
  entries.forEach(function (entry) {
    var rv = _getAxisValueLabel(entry, rowAxisKey);
    var cv = _getAxisValueLabel(entry, colAxisKey);
    var key = rv + "::" + cv;
    if (!lookup[key]) lookup[key] = [];
    lookup[key].push(entry);
  });
  var isColPrompt = colAxisKey === "prompt";
  // Header row
  var headerRow = el("div", { class: "comfymodal-studio-experiment-grid-row" });
  headerRow.appendChild(el("div", { class: "comfymodal-studio-experiment-grid-corner", text: colAxisKey }));
  var colHeaderCells = el("div", { class: "comfymodal-studio-experiment-grid-row-cells" });
  colVals.forEach(function (cv) {
    var colHeaderEl = el("div", {
      class: "comfymodal-studio-experiment-grid-header" + (isColPrompt ? " is-prompt" : ""),
    });
    if (isColPrompt) {
      colHeaderEl.appendChild(el("span", {
        class: "comfymodal-studio-experiment-grid-header-prompt-text",
        text: cv,
        title: cv,
      }));
    } else {
      colHeaderEl.textContent = cv;
    }
    colHeaderCells.appendChild(colHeaderEl);
  });
  headerRow.appendChild(colHeaderCells);
  container.appendChild(headerRow);
  var isRowPrompt = rowAxisKey === "prompt";
  var _matCellIdx = 0;
  // Data rows
  rowVals.forEach(function (rv) {
    var dataRow = el("div", { class: "comfymodal-studio-experiment-grid-row" });
    var rowLabelEl = el("div", {
      class: "comfymodal-studio-experiment-grid-row-label" + (isRowPrompt ? " is-prompt" : ""),
    });
    if (isRowPrompt) {
      rowLabelEl.appendChild(el("span", {
        class: "comfymodal-studio-experiment-grid-row-label-prompt-text",
        text: rv,
        title: rv,
      }));
    } else {
      rowLabelEl.textContent = rv;
    }
    dataRow.appendChild(rowLabelEl);
    var dataCells = el("div", { class: "comfymodal-studio-experiment-grid-row-cells" });
    colVals.forEach(function (cv) {
      var key = rv + "::" + cv;
      var cellEntries = lookup[key];
      if (cellEntries && cellEntries.length > 0) {
        var stack = el("div", { class: "comfymodal-studio-experiment-grid-cell-stack" });
        cellEntries.forEach(function (entry, idx) {
          entry._axisLabels = entry._axisLabels || {};
          entry._axisLabels[rowAxisKey] = rv;
          entry._axisLabels[colAxisKey] = cv;
          extraAxes.forEach(function (ax) {
            entry._axisLabels[ax] = _getAxisValueLabel(entry, ax);
          });
          stack.appendChild(_renderExperimentCell(entry, apiBase, state, context, _matCellIdx));
          _matCellIdx++;
        });
        dataCells.appendChild(stack);
      } else {
        dataCells.appendChild(_renderEmptyCell(""));
      }
    });
    dataRow.appendChild(dataCells);
    container.appendChild(dataRow);
  });
  gridOuter.appendChild(container);
}

function _getCellDuration(attempt) {
  if (!attempt) return null;

  // Safe number conversion: returns null for non-numeric inputs
  function _toNum(v) {
    if (v == null) return null;
    if (typeof v === "number") return v;
    if (typeof v === "string") {
      var n = Number(v);
      return isNaN(n) ? null : n;
    }
    return null;
  }

  // 1. Truthful total/runtime fields (top-level)
  var _topFields = ["duration_ms", "durationMs", "duration", "end_to_end_total_ms"];
  for (var _i = 0; _i < _topFields.length; _i++) {
    var _tv = _toNum(attempt[_topFields[_i]]);
    if (_tv != null) return _tv;
  }

  // 2. timing_payload: extract total from trace/deltas_ms or its own fields
  if (attempt.timing_payload && typeof attempt.timing_payload === "object") {
    var tp = attempt.timing_payload;
    var tpTotal = _toNum(tp.total_ms) || _toNum(tp.end_to_end_total_ms) || _toNum(tp.duration_ms);
    if (tpTotal != null) return tpTotal;
    // Sum deltas_ms if trace/deltas_ms is present
    if (tp.trace && typeof tp.trace === "object") {
      // Prefer explicit parent totals in trace (non-overlapping)
      var traceTotal = _toNum(tp.trace.end_to_end_total_ms);
      if (traceTotal != null) return traceTotal;
      // Check derived_ms totals
      if (tp.trace.derived_ms && typeof tp.trace.derived_ms === "object") {
        var derivedTotal = _toNum(tp.trace.derived_ms.end_to_end_total_ms);
        if (derivedTotal != null) return derivedTotal;
      }
      // Check deltas_ms parent totals (not child stages)
      if (tp.trace.deltas_ms && typeof tp.trace.deltas_ms === "object") {
        var infTotal = _toNum(tp.trace.deltas_ms.inference_total) || _toNum(tp.trace.deltas_ms.remote_inference_total);
        if (infTotal != null) return infTotal;
        // No parent total found — sum non-overlapping child stages only
        var childKeys = ["clip_load", "clip_encode", "sampler", "vae_decode", "image_io", "output_transfer"];
        var sum = 0;
        var hasAny = false;
        for (var ci = 0; ci < childKeys.length; ci++) {
          var cv = _toNum(tp.trace.deltas_ms[childKeys[ci]]);
          if (cv != null) { sum += cv; hasAny = true; }
        }
        if (hasAny) return sum;
      }
    }
  }

  // 3. timings object (backward compat) — but NOT restore-only timing
  if (attempt.timings && typeof attempt.timings === "object") {
    var timTotal = _toNum(attempt.timings.end_to_end_total_ms) || _toNum(attempt.timings.total_ms);
    if (timTotal != null) return timTotal;
  }

  // 4. Fallback: scheduler_execution_ms (inference/scheduler, only when present)
  var schedVal = _toNum(attempt.scheduler_execution_ms);
  if (schedVal != null) return schedVal;
  if (attempt.timings && typeof attempt.timings === "object") {
    var schedTim = _toNum(attempt.timings.scheduler_execution_ms);
    if (schedTim != null) return schedTim;
  }

  // NOT returned: restore-only timing (remote_timings.restore_total_ms)
  return null;
}

function _buildCellMetaRows(entry) {
  var attempt = entry.attempt || {};
  var axisValues = entry.cell.axis_values || {};
  var rows = [];

  // Helper: get value from attempt metadata first, then axis_values as fallback
  function _val(key) {
    if (attempt[key] != null && attempt[key] !== "" && String(attempt[key]) !== "?") return attempt[key];
    if (axisValues[key] != null && axisValues[key] !== "" && String(axisValues[key]) !== "?") return axisValues[key];
    return null;
  }

  // Helper: check sentinel/empty values
  function _isSentinel(v) {
    var sv = v != null ? (typeof v === "object" ? JSON.stringify(v) : String(v)) : "";
    return sv === "?" || sv === "" || sv.indexOf("__COMFYMODAL_WORKFLOW_OWNED__") >= 0;
  }

  // 1. Model row: unet > model > checkpoint_id (attempt then axis_values)
  var modelVal = _val("unet") || _val("model") || _val("checkpoint_id");
  if (modelVal != null && !_isSentinel(modelVal)) {
    rows.push({ key: "Model", val: String(modelVal) });
  }

  // 2. LoRA row: lora_chain (attempt then axis_values)
  var loraVal = _val("lora_chain");
  if (loraVal != null) {
    if (Array.isArray(loraVal)) {
      if (loraVal.length > 0) {
        var loraParts = loraVal.map(function(l) {
          if (typeof l === "object" && l != null) {
            return (l.name || l.model || "") + (l.strength != null ? " (" + l.strength + ")" : "");
          }
          return String(l);
        });
        rows.push({ key: "LoRA", val: loraParts.join(", ") });
      }
      // else omit empty lora_chain array
    } else {
      var loraStr = String(loraVal);
      if (!_isSentinel(loraStr)) {
        rows.push({ key: "LoRA", val: loraStr });
      }
    }
  }

  // 3. Sampler
  var samplerVal = _val("sampler");
  if (samplerVal != null && !_isSentinel(samplerVal)) {
    rows.push({ key: "Sampler", val: String(samplerVal) });
  }

  // 4. Scheduler
  var schedulerVal = _val("scheduler");
  if (schedulerVal != null && !_isSentinel(schedulerVal)) {
    rows.push({ key: "Scheduler", val: String(schedulerVal) });
  }

  // 5. Guidance / CFG
  var guidanceVal = _val("guidance");
  if (guidanceVal != null && !_isSentinel(guidanceVal)) {
    rows.push({ key: "Guidance", val: String(guidanceVal) });
  }

  // 6. Steps
  var stepsVal = _val("steps");
  if (stepsVal != null && !_isSentinel(stepsVal)) {
    rows.push({ key: "Steps", val: String(stepsVal) });
  }

  // 7. Denoise
  var denoiseVal = _val("denoise");
  if (denoiseVal != null && !_isSentinel(denoiseVal)) {
    rows.push({ key: "Denoise", val: String(denoiseVal) });
  }

  // 8. Prompt (attempt metadata, then cell.prompt, then axis_values)
  var promptVal = attempt.prompt != null && attempt.prompt !== ""
    ? attempt.prompt
    : (entry.cell.prompt != null && entry.cell.prompt !== ""
        ? entry.cell.prompt
        : _val("prompt"));
  if (promptVal != null && promptVal !== "") {
    var shortP = String(promptVal);
    if (shortP.length > 50) shortP = shortP.substring(0, 48) + "\u2026";
    rows.push({ key: "Prompt", val: shortP, full: String(promptVal) });
  }

  // 9. Negative prompt (attempt metadata, then axis_values)
  var negPromptVal = _val("negative_prompt");
  if (negPromptVal != null && negPromptVal !== "") {
    var shortNeg = String(negPromptVal);
    if (shortNeg.length > 50) shortNeg = shortNeg.substring(0, 48) + "\u2026";
    rows.push({ key: "Negative", val: shortNeg, full: String(negPromptVal) });
  }

  // 10. Size (width x height)
  var w = _val("width");
  var h = _val("height");
  if (w != null && h != null && !_isSentinel(w) && !_isSentinel(h)) {
    rows.push({ key: "Size", val: String(w) + "\u00d7" + String(h) });
  }

  // 11. Seed
  var seedVal = _val("seed");
  if (seedVal != null && !_isSentinel(seedVal)) {
    rows.push({ key: "Seed", val: String(seedVal) });
  }

  // Extra varying axes not already covered (preserves existing sentinel filtering)
  var covered = {};
  for (var ci = 0; ci < rows.length; ci++) covered[rows[ci].key.toLowerCase()] = true;
  for (var ax in axisValues) {
    if (!Object.prototype.hasOwnProperty.call(axisValues, ax)) continue;
    if (typeof ax === "string" && ax.indexOf("__") === 0) continue;
    var rawVal = axisValues[ax];
    var sv = rawVal != null ? (typeof rawVal === "object" ? JSON.stringify(rawVal) : String(rawVal)) : "";
    if (sv.indexOf("__COMFYMODAL_WORKFLOW_OWNED__") >= 0 || sv === "" || sv === "?") continue;
    var lowAx = ax.toLowerCase();
    if (covered[lowAx]) continue;
    var ctrlDef = CONTROL_DEFS[ax];
    var displayLabel = ctrlDef ? ctrlDef.label : ax;
    rows.push({ key: displayLabel, val: sv });
    covered[lowAx] = true;
  }

  return rows;
}

function _renderEmptyCell(label) {
  return el("div", {
    class: "comfymodal-studio-experiment-grid-cell comfymodal-studio-experiment-grid-cell-empty",
    text: label || "",
  });
}

function _renderExperimentCell(entry, apiBase, state, context, index) {
  var ck = entry.cell.cell_key;
  var attempt = entry.attempt || {};
  var status = attempt.status || "pending";
  var outputUrl = entry.outputUrl;
  var isCompleted = status === "completed" || status === "succeeded" || status === "done";
  var isFailed = status === "failed" || status === "error";
  var isSkipped = status === "skipped";
  var isInterrupted = status === "interrupted";
  var isRunning = status === "running" || status === "in_progress";
  var isPending = !isCompleted && !isFailed && !isRunning && !isSkipped && !isInterrupted;

  var isSelected = state.playground && state.playground._selectedCellKey === ck;

  var cell = el("button", {
    type: "button",
    class: "comfymodal-studio-experiment-grid-cell"
      + (isCompleted ? " completed" : "")
      + (isFailed ? " failed" : "")
      + (isSkipped ? " skipped" : "")
      + (isInterrupted ? " interrupted" : "")
      + (isRunning ? " running" : "")
      + (isPending ? " pending" : "")
      + (isSelected ? " selected" : ""),
    "data-testid": "experiment-cell-" + ck,
    "data-cell-key": ck,
    "data-cell-status": status,
    tabindex: isSelected ? "0" : "-1", // Roving tabindex for arrow navigation
  });

  var card = el("div", { class: "cm-exp-cell-card" });

  // ── Image wrapper ──────────────────────────────────────────────
  var imgwrap = el("div", { class: "cm-exp-cell-imgwrap" });

  if (outputUrl) {
    imgwrap.style.aspectRatio = "auto";
    imgwrap.appendChild(el("img", {
      class: "cm-exp-cell-image",
      src: outputUrl,
      alt: "Cell " + ck,
      loading: "lazy",
    }));
  } else if (isRunning) {
    imgwrap.appendChild(el("div", { class: "cm-exp-cell-loading", "data-testid": "cell-loading-" + ck }));
  } else if (isCompleted) {
    imgwrap.appendChild(el("div", { class: "cm-exp-cell-icon cm-exp-cell-icon-done", text: "\u2713" }));
  } else if (isFailed) {
    imgwrap.appendChild(el("div", { class: "cm-exp-cell-icon cm-exp-cell-icon-fail", text: "\u2717" }));
  } else if (isSkipped) {
    imgwrap.appendChild(el("div", { class: "cm-exp-cell-icon cm-exp-cell-icon-skip", text: "\u21b7" }));
  } else if (isInterrupted) {
    imgwrap.appendChild(el("div", { class: "cm-exp-cell-icon cm-exp-cell-icon-interrupt", text: "\u23f8" }));
  } else {
    imgwrap.appendChild(el("div", { class: "cm-exp-cell-placeholder" }));
  }

  // Order badge (#N)
  if (index != null) {
    imgwrap.appendChild(el("span", {
      class: "cm-exp-cell-badge cm-exp-cell-index",
      text: "#" + (index + 1),
    }));
  }

  // Runtime badge
  var durationMs = _getCellDuration(attempt);
  if (durationMs != null && durationMs > 0) {
    imgwrap.appendChild(el("span", {
      class: "cm-exp-cell-badge cm-exp-cell-time",
      text: _formatDuration(durationMs),
      title: (typeof durationMs === "number" ? durationMs : Number(durationMs)).toFixed(0) + "ms",
    }));
  }

  card.appendChild(imgwrap);
  cell.appendChild(card);

  // Click handler — select cell for detail view
  cell.addEventListener("click", function () {
    if (state.playground) {
      if (state.playground._selectedCellKey === ck) {
        state.playground._selectedCellKey = null;
      } else {
        state.playground._selectedCellKey = ck;
      }
      if (context && context.setPage) context.setPage("playground");
    }
  });

  // Focus handler — maintain roving tabindex (the focused cell gets tabindex 0)
  cell.addEventListener("focus", function () {
    var allCells = cell.closest("[data-testid='experiment-grid-viewport']")
      ? cell.closest("[data-testid='experiment-grid-viewport']").querySelectorAll(".comfymodal-studio-experiment-grid-cell")
      : [];
    for (var ci = 0; ci < allCells.length; ci++) {
      allCells[ci].setAttribute("tabindex", allCells[ci] === cell ? "0" : "-1");
    }
  });

  return cell;
}

// ── Spatial Arrow Navigation for Experiment Grid ──────────────────────────
//
// Attaches an arrow-key handler to the experiment grid viewport that navigates
// between cells using actual rendered DOM geometry (getBoundingClientRect).
// Directional distance with perpendicular tie-break, deterministic no wrap.
// Keeps text/numeric/control inputs from intercepting keys.
//
// Call once after the grid renders. Returns a cleanup function.

function _enableGridArrowNavigation(gridViewport) {
  if (!gridViewport) return function () {};

  function _onGridKeydown(e) {
    // Only handle Arrow keys
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown" && e.key !== "ArrowLeft" && e.key !== "ArrowRight") {
      return;
    }

    // If an editable control has focus, do NOT intercept (let the control handle it)
    var active = document.activeElement;
    if (active) {
      var tag = active.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || active.isContentEditable) {
        // For number inputs, allow up/down for step adjustment
        if ((e.key === "ArrowUp" || e.key === "ArrowDown") && tag === "INPUT" && active.type === "number") {
          return; // Let the native input handle step
        }
        // For text inputs, left/right should move cursor
        if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && (tag === "INPUT" || tag === "TEXTAREA")) {
          return; // Let the native input handle cursor movement
        }
        // For all other editable controls with arrow keys, do not intercept
        // unless the focus is specifically on a grid cell
      }
    }

    // Only navigate if the active element (or the viewport itself) is within our grid
    var gridCells = gridViewport.querySelectorAll(".comfymodal-studio-experiment-grid-cell");
    if (gridCells.length === 0) return;

    var currentCell = null;
    if (active && active.classList && active.classList.contains("comfymodal-studio-experiment-grid-cell")) {
      currentCell = active;
    } else {
      // If no cell is focused, focus the first cell (or the last selected one)
      var selected = gridViewport.querySelector('.comfymodal-studio-experiment-grid-cell.selected');
      currentCell = selected || gridCells[0];
      if (currentCell) {
        e.preventDefault();
        currentCell.focus();
        currentCell.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
      return;
    }

    e.preventDefault();

    // Get geometry of the current cell
    var currentRect = currentCell.getBoundingClientRect();
    var cx = currentRect.left + currentRect.width / 2;
    var cy = currentRect.top + currentRect.height / 2;

    // Define directional search: for each candidate cell, compute distance
    // weighted by direction. The best candidate is the one with minimal
    // effective distance in the given direction.
    var bestCell = null;
    var bestDist = Infinity;
    var bestPerpDist = Infinity;

    for (var i = 0; i < gridCells.length; i++) {
      var candidate = gridCells[i];
      if (candidate === currentCell || candidate.disabled) continue;

      var cr = candidate.getBoundingClientRect();
      var ccx = cr.left + cr.width / 2;
      var ccy = cr.top + cr.height / 2;

      var dx = ccx - cx;
      var dy = ccy - cy;
      var dist = Math.sqrt(dx * dx + dy * dy);
      var perpDist = 0;

      switch (e.key) {
        case "ArrowUp":
          if (dy >= 0) continue; // Only cells above
          perpDist = Math.abs(dx);
          break;
        case "ArrowDown":
          if (dy <= 0) continue; // Only cells below
          perpDist = Math.abs(dx);
          break;
        case "ArrowLeft":
          if (dx >= 0) continue; // Only cells to the left
          perpDist = Math.abs(dy);
          break;
        case "ArrowRight":
          if (dx <= 0) continue; // Only cells to the right
          perpDist = Math.abs(dy);
          break;
      }

      // Primary: directional distance (closest in the pressed direction);
      // tie-break: perpendicular distance (same row/column alignment)
      if (dist < bestDist || (dist === bestDist && perpDist < bestPerpDist)) {
        bestCell = candidate;
        bestDist = dist;
        bestPerpDist = perpDist;
      }
    }

    if (bestCell) {
      // Update roving tabindex
      for (var j = 0; j < gridCells.length; j++) {
        gridCells[j].setAttribute("tabindex", gridCells[j] === bestCell ? "0" : "-1");
      }
      bestCell.focus();
      bestCell.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  // Capture phase to intercept before editable controls
  gridViewport.addEventListener("keydown", _onGridKeydown);

  return function () {
    gridViewport.removeEventListener("keydown", _onGridKeydown);
  };
}

function _renderExperimentProgressBars(runState, state) {
  var container = el("div", {
    class: "comfymodal-studio-experiment-grid-progress",
    "data-testid": "experiment-grid-progress",
  });

  var counters = (runState && runState._snapshot && runState._snapshot.counters) || {};
  var total = runState && runState._snapshot && runState._snapshot.total_cells;
  var completed = counters.completed || 0;
  var failed = counters.failed || 0;
  var skipped = counters.skipped || 0;
  var interrupted = counters.interrupted || 0;
  var terminalTotal = completed + failed + skipped + interrupted;
  var totalCells = total || terminalTotal || 0;
  var isMultiCell = totalCells > 1;

  // Bar 1: Current cell / image progress (from scoped tracker sampler).
  // Only rendered when sampler telemetry has arrived (max > 0).
  // Without real sampler data, no swinging indeterminate bar — for
  // multi-cell experiments, total cell progress is the primary indicator.
  var currentPct = runState && runState.samplerPercent;
  var hasSamplerData = runState && runState.samplerMaximum > 0 && runState.samplerStep != null;
  if (hasSamplerData && currentPct != null) {
    // Determinate: sampler step / max known
    var currentBarRow = el("div", { class: "comfymodal-studio-experiment-grid-progress-row" });
    currentBarRow.appendChild(el("span", {
      class: "comfymodal-studio-experiment-grid-progress-label",
      text: "Current image",
    }));
    var currentBarTrack = el("div", { class: "comfymodal-studio-experiment-grid-progress-track" });
    var currentBarFill = el("div", {
      class: "comfymodal-studio-experiment-grid-progress-fill",
      style: "width:" + Math.max(0, Math.min(100, currentPct)) + "%;",
    });
    currentBarTrack.appendChild(currentBarFill);
    currentBarRow.appendChild(currentBarTrack);
    currentBarRow.appendChild(el("span", {
      class: "comfymodal-studio-experiment-grid-progress-pct",
      text: Math.round(currentPct) + "%",
    }));
    container.appendChild(currentBarRow);
  } else if (!isMultiCell) {
    // Single-cell experiment without sampler data: show a compact
    // waiting state without the swinging indeterminate animation.
    var currentBarRow = el("div", { class: "comfymodal-studio-experiment-grid-progress-row" });
    currentBarRow.appendChild(el("span", {
      class: "comfymodal-studio-experiment-grid-progress-label",
      text: "Current image",
    }));
    var currentBarTrack = el("div", { class: "comfymodal-studio-experiment-grid-progress-track" });
    var currentBarFill = el("div", {
      class: "comfymodal-studio-experiment-grid-progress-fill",
      style: "width:8%;background:#333;",
    });
    currentBarTrack.appendChild(currentBarFill);
    currentBarRow.appendChild(currentBarTrack);
    currentBarRow.appendChild(el("span", {
      class: "comfymodal-studio-experiment-grid-progress-pct",
      text: "Starting\u2026",
      style: "font-size:9px;color:#888;font-style:italic;",
    }));
    container.appendChild(currentBarRow);
  }
  // Multi-cell without sampler data: omit the "Current image" row entirely
  // — total cell progress is the meaningful indicator.

  // Bar 2: Total cells progress (all terminal states matter)
  var cellPct = totalCells > 0 ? (terminalTotal / totalCells) * 100 : 0;
  var cellBarRow = el("div", { class: "comfymodal-studio-experiment-grid-progress-row" });
  cellBarRow.appendChild(el("span", {
    class: "comfymodal-studio-experiment-grid-progress-label",
    text: "Total cells",
  }));
  var cellBarTrack = el("div", { class: "comfymodal-studio-experiment-grid-progress-track" });
  var cellBarFill = el("div", {
    class: "comfymodal-studio-experiment-grid-progress-fill",
    style: "width:" + Math.max(0, Math.min(100, cellPct)) + "%;",
  });
  cellBarTrack.appendChild(cellBarFill);
  cellBarRow.appendChild(cellBarTrack);
  // Show breakdown: completed/failed/skipped/interrupted/total
  var breakdownParts = [];
  if (completed > 0) breakdownParts.push(completed + " done");
  if (failed > 0) breakdownParts.push(failed + " failed");
  if (skipped > 0) breakdownParts.push(skipped + " skipped");
  if (interrupted > 0) breakdownParts.push(interrupted + " interrupted");
  var breakdownText = breakdownParts.length > 0 ? breakdownParts.join(", ") + " / " + totalCells : terminalTotal + "/" + totalCells;
  cellBarRow.appendChild(el("span", {
    class: "comfymodal-studio-experiment-grid-progress-pct",
    text: breakdownText,
  }));
  container.appendChild(cellBarRow);

  return container;
}

function _renderCellDetailOverlay(entry, entries, apiBase, state, context, varyingAxes) {
  varyingAxes = varyingAxes || [];
  entries = entries || [];

  var previousPreview = state.playground && state.playground._cellPreviewController;
  if (previousPreview && typeof previousPreview.close === "function") {
    previousPreview.close(false);
  }
  if (state.playground) state.playground._cellPreviewController = null;

  function _close() {
    if (state.playground) state.playground._selectedCellKey = null;
    if (state.playground) state.playground._cellPreviewController = null;
    if (context && context.setPage) context.setPage("playground");
  }

  // ── Arrow-key cell navigation through the grid ───────────────────
  // Uses spatial geometry: for each arrow direction, query all rendered
  // grid cell DOM nodes, compute distances from the current cell center,
  // and pick the closest candidate in the pressed direction.  No wrapping
  // at edges.  On selection, updates _selectedCellKey and re-renders.
  var onKeyDown = function (e) {
    var key = e.key;
    if (key !== "ArrowUp" && key !== "ArrowDown" && key !== "ArrowLeft" && key !== "ArrowRight") return false;
    var currentKey = state.playground && state.playground._selectedCellKey;
    if (!currentKey) return false;
    var viewport = document.querySelector('[data-testid="experiment-grid-viewport"]');
    if (!viewport) return false;
    var allCells = viewport.querySelectorAll(".comfymodal-studio-experiment-grid-cell");
    if (allCells.length === 0) return false;
    var currentCell = null;
    for (var _ci = 0; _ci < allCells.length; _ci++) {
      if (allCells[_ci].getAttribute("data-cell-key") === currentKey) { currentCell = allCells[_ci]; break; }
    }
    if (!currentCell) return false;
    var cr = currentCell.getBoundingClientRect();
    var cx = cr.left + cr.width / 2;
    var cy = cr.top + cr.height / 2;
    var bestCell = null, bestDist = Infinity, bestPerp = Infinity;
    for (var _cj = 0; _cj < allCells.length; _cj++) {
      if (allCells[_cj] === currentCell) continue;
      var nr = allCells[_cj].getBoundingClientRect();
      var ncx = nr.left + nr.width / 2;
      var ncy = nr.top + nr.height / 2;
      var dx = ncx - cx, dy = ncy - cy;
      if (key === "ArrowUp" && dy >= 0) continue;
      if (key === "ArrowDown" && dy <= 0) continue;
      if (key === "ArrowLeft" && dx >= 0) continue;
      if (key === "ArrowRight" && dx <= 0) continue;
      var dist = Math.sqrt(dx * dx + dy * dy);
      var perp = (key === "ArrowUp" || key === "ArrowDown") ? Math.abs(dx) : Math.abs(dy);
      // Primary: directional distance; tie-break: perpendicular distance
      if (dist < bestDist || (dist === bestDist && perp < bestPerp)) {
        bestDist = dist; bestPerp = perp; bestCell = allCells[_cj];
      }
    }
    if (bestCell) {
      var newKey = bestCell.getAttribute("data-cell-key");
      if (newKey && state.playground) {
        state.playground._selectedCellKey = newKey;
        if (context && context.setPage) {
          e.preventDefault();
          if (state.playground._cellPreviewController) {
            state.playground._cellPreviewController.close(false);
            state.playground._cellPreviewController = null;
          }
          context.setPage("playground");
        }
        return true;
      }
    }
    return false;
  };

  var sections = [];

  // Status
  sections.push(el("div", {
    class: "comfymodal-studio-experiment-grid-detail-status",
    text: "Status: " + (entry.attempt.status || "unknown"),
  }));

  // ── Axis values ───────────────────────────────────────────
  var av = entry.cell.axis_values || {};
  var allAxisKeys = Object.keys(av).filter(function (k) {
    if (typeof k === "string" && k.indexOf("__") === 0) return false;
    var rawVal = av[k];
    var sv = rawVal != null ? (typeof rawVal === "object" ? JSON.stringify(rawVal) : String(rawVal)) : "";
    if (sv.indexOf("__COMFYMODAL_WORKFLOW_OWNED__") >= 0) return false;
    return true;
  });
  var varyingKeys = allAxisKeys.filter(function (k) { return varyingAxes.indexOf(k) >= 0; });
  var nonVaryingKeys = allAxisKeys.filter(function (k) { return varyingAxes.indexOf(k) < 0; });
  var hasPrompt = entry.cell.prompt != null && entry.cell.prompt !== "";
  var hasAnyAxes = varyingKeys.length > 0 || nonVaryingKeys.length > 0 || hasPrompt;

  if (hasAnyAxes) {
    var axisSection = el("div", { class: "comfymodal-studio-experiment-grid-detail-axes" });
    axisSection.appendChild(el("div", {
      class: "comfymodal-studio-experiment-grid-detail-axes-title",
      text: "Axis Values",
    }));

    if (hasPrompt) {
      var promptVal = String(entry.cell.prompt);
      if (promptVal.length > 200) promptVal = promptVal.substring(0, 200) + "\u2026";
      axisSection.appendChild(el("div", {
        class: "comfymodal-studio-experiment-grid-detail-axis-row",
        "data-testid": "detail-axis-row-prompt",
      }, [
        el("span", { class: "comfymodal-studio-experiment-grid-detail-axis-key", text: "Prompt: " }),
        el("span", { class: "comfymodal-studio-experiment-grid-detail-axis-value", text: promptVal }),
      ]));
    }

    varyingKeys.forEach(function (key) {
      var ctrlDef = CONTROL_DEFS[key];
      var label = ctrlDef ? ctrlDef.label : key;
      var val = _getAxisValueLabel(entry, key);
      axisSection.appendChild(el("div", {
        class: "comfymodal-studio-experiment-grid-detail-axis-row",
        "data-testid": "detail-axis-row-" + key,
      }, [
        el("span", { class: "comfymodal-studio-experiment-grid-detail-axis-key", text: label + ": " }),
        el("span", { class: "comfymodal-studio-experiment-grid-detail-axis-value", text: val }),
      ]));
    });

    if (nonVaryingKeys.length > 0) {
      var nvToggle = el("button", {
        class: "comfymodal-studio-experiment-grid-detail-nonvarying-toggle",
        "data-testid": "detail-nonvarying-toggle",
        type: "button",
        "aria-expanded": "false",
        text: "\u25b6 Non-varying (" + nonVaryingKeys.length + ")",
      });
      var nvContent = el("div", {
        class: "comfymodal-studio-experiment-grid-detail-nonvarying-content",
        "data-testid": "detail-nonvarying-content",
      });
      nonVaryingKeys.forEach(function (key) {
        var ctrlDef = CONTROL_DEFS[key];
        var label = ctrlDef ? ctrlDef.label : key;
        var val = _getAxisValueLabel(entry, key);
        nvContent.appendChild(el("div", {
          class: "comfymodal-studio-experiment-grid-detail-nonvarying-row",
          "data-testid": "detail-nonvarying-row-" + key,
        }, [
          el("span", { class: "comfymodal-studio-experiment-grid-detail-nonvarying-key", text: label + ": " }),
          el("span", { class: "comfymodal-studio-experiment-grid-detail-nonvarying-value", text: val }),
        ]));
      });
      nvToggle.addEventListener("click", function () {
        var isOpen = nvContent.classList.contains("is-visible");
        nvContent.classList.toggle("is-visible");
        nvToggle.textContent = isOpen ? "\u25b6 Non-varying (" + nonVaryingKeys.length + ")" : "\u25bc Non-varying (" + nonVaryingKeys.length + ")";
        nvToggle.setAttribute("aria-expanded", !isOpen ? "true" : "false");
      });
      axisSection.appendChild(nvToggle);
      axisSection.appendChild(nvContent);
    }

    // The axis section renders as a right-side vertical column beside the
    // image (sideColumn) so it never shifts the centered image.
    axisSection.style.cssText = "border-top:none;padding-top:0;min-width:180px;";
  }

  // Preset / backend info
  if (entry.attempt.checkpoint_id != null) {
    sections.push(el("div", {
      class: "comfymodal-studio-experiment-grid-detail-checkpoint",
      text: "Checkpoint: " + entry.attempt.checkpoint_id,
    }));
  }

  // Save-output support (single-output backend action).  The button is
  // only offered when the cell carries a run id, has an output, and the
  // record is not already saved.
  var saveOutput = null;
  var cellRunId = entry.attempt.run_id || entry.attempt.attempt_id || "";
  var cellSaved = !!(entry.attempt.output_saved === true || (entry.attempt.extra && entry.attempt.extra.output_saved === true));
  if (entry.outputUrl && cellRunId && !cellSaved) {
    saveOutput = {
      saved: false,
      onSave: async function () {
        var res = await saveRunOutput(apiBase, cellRunId, { output_index: 0 });
        if (!res || res.status !== "ok") {
          throw new Error((res && res.message) || "Save request failed");
        }
        entry.attempt.output_saved = true;
        if (state.playground && state.playground._cellPreviewController) {
          state.playground._cellPreviewController.close(false);
          state.playground._cellPreviewController = null;
        }
        if (context && context.setPage) context.setPage("playground");
        return true;
      },
    };
  }

  var preview = createImagePreviewOverlay({
    imageUrl: entry.outputUrl || null,
    alt: "Cell output",
    onClose: _close,
    onKeyDown: onKeyDown,
    sections: sections,
    sideColumn: hasAnyAxes ? axisSection : null,
    saveOutput: saveOutput,
  });

  if (state.playground) state.playground._cellPreviewController = preview;

  return preview.overlay;
}

function _formatDuration(ms) {
  if (ms == null) return "0ms";
  // Safe numeric conversion — never call .toFixed on a non-number
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

// ── DOM Progress Patch (avoids full page teardown for frequent updates) ──

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

// ── Favorite Star ────────────────────────────────────────────────────────

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
    updateRunAnnotation(apiBase, runId, { favorite: newFav }).then(function (result) {
      if (!result || result.status !== "ok") {
        // Rollback on failure
        isFav = wasFav;
        nr.favorite = wasFav;
        star.textContent = wasFav ? "\u2605" : "\u2606";
        star.style.color = wasFav ? "#fbbf24" : "#555";
        star.setAttribute("aria-label", wasFav ? "Remove from favorites" : "Add to favorites");
        star.setAttribute("aria-pressed", wasFav ? "true" : "false");
        star.title = wasFav ? "Remove from favorites" : "Add to favorites";
      }
    });
  });

  return star;
}

// ── Note Editor ──────────────────────────────────────────────────────────

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

    updateRunAnnotation(apiBase, runId, { note: textarea.value }).then(function (result) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save";
      if (result && result.status === "ok") {
        savedNote = textarea.value;
        nr.note = textarea.value;
        // Use backend updated_at as primary source, fall back to client time
        var backendUpdatedAt = result.annotations && result.annotations.updated_at;
        nr.noteUpdatedAt = backendUpdatedAt || new Date().toISOString();
        isDirty = false;
        statusEl.textContent = "Saved " + nr.noteUpdatedAt.substring(0, 19);
        statusEl.style.color = "#4ade80";
      } else {
        statusEl.textContent = "Save failed";
        statusEl.style.color = "#f87171";
      }
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

// ── Right Workspace ──────────────────────────────────────────────────────

function renderWorkspace(state, context) {
  const workspace = el("div", { class: "comfymodal-studio-workspace", "data-testid": "workspace" });

  // When experiment mode is active and the poller has delivered snapshot
  // data, show the experiment grid instead of the normal single-run UI.
  var _pg = state.playground;
  var _rs = _pg && _pg.runState;
  var _showGrid = _pg && _pg.experimentMode && _rs && _rs._snapshot;
  if (_showGrid) {
    workspace.appendChild(renderExperimentGridViewport(state, context));
    return workspace;
  }

  // Normal single-run UI (non-experiment or no active experiment data)
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
      && runState.status !== "completed"
      && runState.status !== "error"
      && runState.status !== "idle";
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

// ── Metadata Section ─────────────────────────────────────────────────────
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
    // No run selected — show only when a canvas result exists
    return section;
  }

  const nr = selectedRun;
  const rc = nr.resolvedControls || {};
  const rqc = nr.requestedControls || {};
  const isFailed = nr.status === "error" || nr.status === "failed";

  // ── Summary block ──────────────────────────────────────────────────
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

  // ── Save Output (single-output backend action) ────────────────────
  // Button visibility follows the record's saved state; the request
  // targets only the selected (primary) output.
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

  // ── Timing Summary Card ────────────────────────────────────────────
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
        tagRow.appendChild(el("span", {
          class: "comfymodal-studio-timing-tag",
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

  // ── Key generation settings (using shared normalizer) ─────────────
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

  // ── Collapsible toggles (Note | Advanced) ──────────────────────────
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

  // ── Note panel (collapsible) ──────────────────────────────────────
  const notePanel = el("div", {
    class: "comfymodal-studio-metadata-note-panel",
    style: "display:none;",
  });
  notePanel.appendChild(renderNoteEditor(nr, actions, apiBase));
  section.appendChild(notePanel);

  // ── Advanced panel (collapsible) ───────────────────────────────────
  const advancedPanel = el("div", {
    class: "comfymodal-studio-metadata-advanced",
    style: "display:none;font-size:10px;color:#666;",
  });

  const advancedItems = [];

  // IDs
  if (nr.id) advancedItems.push({ label: "Run ID", value: nr.id });
  if (nr.experimentId) advancedItems.push({ label: "Experiment ID", value: nr.experimentId });
  if (nr.snapshotId) advancedItems.push({ label: "Snapshot ID", value: nr.snapshotId });

  // Full timings — keep raw JSON accessible in advanced diagnostics
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

    // Waterfall summary (serialized v2 report) — same display text as
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

// ── Carousel ────────────────────────────────────────────────────────────
//
// Image carousel of thumbnails from recent image-producing runs.
// Clicking a thumbnail updates the main canvas output.
// Only image-producing runs are shown.

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
    carousel.appendChild(el("p", {
      class: "comfymodal-studio-empty-state",
      text: "Recent runs cleared. Submit a new run to see results here.",
      style: "font-size:var(--font-size-xs);color:var(--color-text-muted);padding:8px;",
    }));
    return carousel;
  }

  if (recentRuns == null) {
    carousel.appendChild(el("p", {
      class: "comfymodal-studio-empty-state",
      text: "Loading recent runs...",
      style: "font-size:var(--font-size-xs);color:var(--color-text-muted);padding:8px;",
    }));

    // Async fetch fills cache — on next render it will show
    refreshRecentRuns(apiBase).then(function () {
      if (carousel.isConnected) rerender();
    });
  } else {
    // ── Hidden state: show reveal bar ──────────────────────────────────
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

    // ── Empty state ────────────────────────────────────────────────────
    if (recentRuns.length === 0) {
      carousel.appendChild(el("p", {
        class: "comfymodal-studio-empty-state",
        text: "Recent runs will appear here once you use the Playground.",
        style: "font-size:var(--font-size-xs);color:var(--color-text-muted);padding:8px;",
      }));
      return carousel;
    }

    // ── Header row with actions ────────────────────────────────────────
    const header = el("div", { class: "comfymodal-studio-carousel-header" });
    header.appendChild(el("span", {
      class: "comfymodal-studio-carousel-header-label",
      text: "Recent runs",
    }));

    const actions = el("div", { class: "comfymodal-studio-carousel-actions" });

    // Clear button — removes all cached and persisted runs
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

    // Close button — hides the carousel (per-session)
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

    recentRuns.forEach(function (nr) {
      const imageUrl = nr.imageUrl;
      const label = nr.presetLabel || nr.presetId || nr.featureId || "Run";
      const isExperiment = Boolean(nr.experimentId);
      const ariaLabel = label + " - " + (nr.status || "") + (imageUrl ? " - Click to view" : " - No image")
        + (isExperiment ? " (experiment)" : "");

      const thumb = el("button", {
        type: "button",
        class: "comfymodal-studio-carousel-item"
          + (nr.status === "completed" || nr.status === "success" || nr.status === "done" ? " completed" : "")
          + (nr.status === "error" || nr.status === "failed" ? " failed" : "")
          + (isExperiment ? " comfymodal-studio-carousel-item-experiment" : ""),
        "aria-label": ariaLabel,
        title: (isExperiment ? "Experiment: " : "") + label + " - " + (nr.status || ""),
        "data-expid": isExperiment ? nr.experimentId : "",
        onclick: function () {
          if (isExperiment && nr.experimentId) {
            // Experiment item — open experiment grid viewport
            loadExperimentIntoPlayground(state, context, nr.experimentId);
          } else if (imageUrl && state.playground) {
            // Ordinary run — update canvas with this run's output
            state.playground.lastRunOutput = imageUrl;
            state.playground._selectedRun = nr;
            rerender();
          }
        },
      });

      if (isExperiment) {
        // Experiment badge overlaid on the thumbnail
        thumb.appendChild(el("span", {
          class: "comfymodal-studio-carousel-exp-badge",
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
      const isOk = nr.status === "completed" || nr.status === "success" || nr.status === "done";
      const isErr = nr.status === "error" || nr.status === "failed";
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
