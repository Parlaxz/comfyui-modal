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
import { runStudioPreset, getStudioRunStatus } from "./studio-backend-api.js";

import {
  getVisibleControlsForPreset,
  getPresetCapabilitySummary,
  getUnavailableControlReasons,
} from "./studio-preset-capabilities.js";
import { resolveRunImageUrl, hasRunImage, normalizeStudioRun, normalizeGenerationSettings } from "./studio-run-normalizer.js";
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
} from "./studio-playground-state.js";
import { getSharedTracker, createScopedTracker } from "./comfymodal-progress.js";
import { updateRunAnnotation } from "./studio-backend-api.js";
import { el } from "./studio-ui.js";

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
             ev.type === "experiment.stopped";
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

    if (status === "queued") {
      if (actions && actions.setRunState) {
        actions.setRunState({ status: "queued", experimentId });
      }
    } else if (status === "in_progress" || status === "running") {
      const progressState = { status: "in_progress", experimentId };
      if (completedCellCount > 0 && totalCells > 0) {
        progressState.cellProgress = completedCellCount + "/" + totalCells;
      }
      if (actions && actions.setRunState) {
        actions.setRunState(progressState);
      }
    } else if (status === "completed" || status === "succeeded") {
      // Require real evidence before showing completed UI
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
          });
        }
      }
      // Without evidence, stay in current state (don't claim completion)
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
  // rather than _hydratedControls (display-only).
  const draft = presetId && featureId ? loadControlDraft(presetId, featureId) : {};
  if (draft && typeof draft === "object" && Object.keys(draft).length > 0) {
    state.playground.controls = draft;
    state.playground._hydratedControls = {};
    return;
  }

  // No draft: build display-only hydrated values from preset defaults
  // and definition defaults (CONTROL_DEFS).  Do NOT carry resolved
  // controls from a previous successful run forward as implicit overrides.
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

function buildEffectiveControls(state, preset, currentFeatureId) {
  const userOverrides = (state.playground && state.playground.controls) || {};
  const visibleIds = getVisibleControlsForPreset(preset, currentFeatureId);
  const controls = {};
  // Only serialize explicit user edits.  Hydrated / preset-default values
  // are display-only — sending them would override the backend's defaults
  // with stale values the user never explicitly confirmed.
  Object.keys(userOverrides).forEach(function (ctrlId) {
    if (visibleIds.indexOf(ctrlId) !== -1) {
      controls[ctrlId] = userOverrides[ctrlId];
    }
  });
  return controls;
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
    const resp = await fetch(apiBase + "/run-history?limit=50");
    if (!resp.ok) { _recentRunsCache = []; return []; }
    const data = await resp.json();
    const entries = (data && data.runs) || [];
    // Filter to Studio runs with images, normalize them
    const studioRuns = entries.filter(function (r) {
      const extra = (r && r.extra) || {};
      const studioMeta = extra.studio_meta || extra.studio_metadata || {};
      return (r.prompt_id && r.prompt_id.indexOf("studio_") === 0) ||
             r.kind === "experiment_cell" ||
             !!(extra.studio_feature_id || extra.studio_preset_id || studioMeta.studio_feature_id || studioMeta.studio_preset_id);
    });
    // Normalize and only keep completed/image-producing runs
    _recentRunsCache = studioRuns.map(function (r) {
      return normalizeStudioRun(r, apiBase);
    }).filter(function (nr) {
      return nr && (nr.status === "completed" || nr.status === "success" || nr.status === "done") && nr.imageUrl;
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
  _recentRunsCache = null;
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

  // 6a. Try to restore from localStorage persisted run result first
  const persistedRun = loadRunResult(targetPresetId, featureId);
  if (persistedRun) {
    state.playground._selectedRun = persistedRun;
    state.playground.lastRunOutput = persistedRun.imageUrl || null;
  } else if (targetPresetId) {
    // 6b. Fallback: fetch server-side recent runs and find latest matching
    await refreshRecentRuns(apiBase);
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
  // getSharedTracker() is still imported for potential secondary uses
  // (e.g., capturing execState bridge values) but is NOT subscribed to
  // for progress UI updates.

  const leftPanel = renderControlPanel(state, context);
  const rightWorkspace = renderWorkspace(state, context);

  container.appendChild(leftPanel);
  container.appendChild(rightWorkspace);

  return container;
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
      }
      const presetId = state.playground.selectedBackendId;
      const featureId = state.playground.featureId;
      const activePreset = getCurrentPresetForSelection(state, presetId);
      clearTimeout(state.playground._draftSaveTimer);
      state.playground._draftSaveTimer = setTimeout(function () {
        const controls = activePreset
          ? buildEffectiveControls(state, activePreset, featureId)
          : Object.assign({}, state.playground.controls || {});
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
      state.playground.runState = { ...state.playground.runState, ...runState };

      // Dispose scoped tracker and clean up local timer on terminal states
      if (runState && (runState.status === "completed" || runState.status === "error")) {
        if (state.playground && state.playground.runState) delete state.playground.runState._localStartTime;
        _disposeScopedTracker(state);
      }

      if (runState && runState.status === "completed") {
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
        });
      } else if (!runState) {
        // Clearing runState — preserve lastRunOutput and _selectedRun so
        // prior result stays visible until new submission enters flight
      }
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
    input = el("textarea", {
      class: "comfymodal-input comfymodal-studio-textarea",
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
        if (actions.setControl) actions.setControl(def.id, parseFloat(input.value) || input.value);
      });
    }
  }

  if (input) group.appendChild(input);
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
    var _now = Date.now();
    if (!_rs2._lastRenderMs || _now - _rs2._lastRenderMs >= 250) {
      _rs2._lastRenderMs = _now;
      if (context && context.setPage) context.setPage("playground");
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

    if (mappedStatus !== rs.status) {
      rs.status = mappedStatus;
    }

    // Trigger re-render on terminal states (dispose tracker) or intermediate
    // progress (throttled to avoid excessive re-renders)
    if (mappedStatus === "completed" || mappedStatus === "error") {
      // Dispose scoped tracker on terminal state
      delete rs._localStartTime;
      _disposeScopedTracker(state);
      if (context && context.setPage) context.setPage("playground");
    } else {
      // Throttle re-renders for intermediate progress
      var now = Date.now();
      if (!rs._lastRenderMs || now - rs._lastRenderMs >= 250) {
        rs._lastRenderMs = now;
        if (context && context.setPage) context.setPage("playground");
      }
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

async function doRunSubmit(state, context, actions) {
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

  if (runState && runState.status === "running") {
    btn.disabled = true;
    btn.textContent = "Running\u2026";
    btn.title = "Run in progress";
    reason.appendChild(el("p", {
      text: "Your run has been submitted\u2026",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    }));
    return container;
  }

  if (runState && runState.status === "submitted") {
    btn.disabled = true;
    btn.textContent = "Submitted";
    btn.title = "Run submitted, waiting for status\u2026";
    reason.appendChild(el("p", {
      text: "Waiting for server response\u2026",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    }));
    _startPolling(container, state, context, actions, runState);
    return container;
  }

  if (runState && runState.status === "waiting") {
    btn.disabled = true;
    btn.textContent = "Waiting\u2026";
    btn.title = "Waiting for experiment to be ready on server";
    reason.appendChild(el("p", {
      text: "Waiting for server setup\u2026",
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    }));
    return container;
  }

  if (runState && (runState.status === "queued" || runState.status === "in_progress")) {
    btn.disabled = true;
    btn.textContent = runState.status === "queued" ? "Queued\u2026" : "Running\u2026";
    btn.title = "Experiment is running";
    const progressText = runState.cellProgress
      ? "Cells completed: " + runState.cellProgress
      : "Run is in progress\u2026";
    reason.appendChild(el("p", {
      text: progressText,
      style: "font-size:var(--font-size-sm);color:var(--color-text-secondary);margin:4px 0 0;",
    }));
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
        const controls = buildEffectiveControls(state, preset, currentFeatureId);

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

        // Capture client-side timestamps at press time (top-level `trace` for server)
        var t0_perf_ms = performance.now();
        var t0_now = Date.now();

        const result = await runStudioPreset(apiBase, {
          presetId: preset.id || selectedId,
          featureId: currentFeatureId,
          controls: controls,
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
  nodesEl.textContent = "Nodes: " + (runState.completedNodes || 0) + "/" + (runState.totalNodes || 0);
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

function _formatDuration(ms) {
  if (ms == null) return "0ms";
  if (ms < 1000) return ms.toFixed(0) + "ms";
  if (ms < 60000) return (ms / 1000).toFixed(1) + "s";
  var m = Math.floor(ms / 60000);
  var s = (ms % 60000) / 1000;
  return m + "m " + s.toFixed(0) + "s";
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

  // ── Note Editor ───────────────────────────────────────────────────
  section.appendChild(renderNoteEditor(nr, actions, apiBase));

  // ── Collapsible advanced details ───────────────────────────────────
  const advancedToggle = el("button", {
    class: "comfymodal-studio-metadata-advanced-toggle",
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
  section.appendChild(advancedToggle);

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
  }

  // Workflow hash
  if (nr.workflowHash) advancedItems.push({ label: "Workflow Hash", value: nr.workflowHash });

  // Output reference
  if (nr.outputPath) advancedItems.push({ label: "Output Path", value: nr.outputPath });
  if (nr.imageUrl) advancedItems.push({ label: "Image URL", value: nr.imageUrl });

  // Resolved controls
  if (Object.keys(nr.resolvedControls).length > 0) {
    advancedItems.push({ label: "Resolved Controls", value: JSON.stringify(nr.resolvedControls, null, 1) });
  }

  // Error
  if (nr.error) advancedItems.push({ label: "Error", value: nr.error });

  advancedItems.forEach(function (item) {
    advancedPanel.appendChild(el("div", { style: "margin:2px 0;" }, [
      el("strong", { text: item.label + ": ", style: "color:#888;" }),
      el("span", { text: (item.value || "").substring(0, 200) + ((item.value || "").length > 200 ? "\u2026" : "") }),
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

  if (recentRuns == null) {
    carousel.appendChild(el("p", {
      class: "comfymodal-studio-empty-state",
      text: "Loading recent runs...",
      style: "font-size:var(--font-size-xs);color:var(--color-text-muted);padding:8px;",
    }));

    // Async fetch fills cache — on next render it will show
    refreshRecentRuns(apiBase).then(function () {
      if (carousel.isConnected && context && context.setPage) {
        context.setPage("playground");
      }
    });
  } else {
    if (recentRuns.length === 0) {
      carousel.appendChild(el("p", {
        class: "comfymodal-studio-empty-state",
        text: "Recent runs will appear here once you use the Playground.",
        style: "font-size:var(--font-size-xs);color:var(--color-text-muted);padding:8px;",
      }));
      return carousel;
    }

    // Carousel track for horizontal scrolling
    const track = el("div", { class: "comfymodal-studio-carousel-track" });

    recentRuns.forEach(function (nr) {
      const imageUrl = nr.imageUrl;
      const label = nr.presetLabel || nr.presetId || nr.featureId || "Run";

      const ariaLabel = label + " - " + (nr.status || "") + (imageUrl ? " - Click to view" : " - No image");
      const thumb = el("button", {
        type: "button",
        class: "comfymodal-studio-carousel-item"
          + (nr.status === "completed" || nr.status === "success" || nr.status === "done" ? " completed" : "")
          + (nr.status === "error" || nr.status === "failed" ? " failed" : ""),
        "aria-label": ariaLabel,
        title: label + " - " + (nr.status || ""),
        onclick: function () {
          // Update canvas with this run's output
          if (imageUrl && state.playground) {
            state.playground.lastRunOutput = imageUrl;
            state.playground._selectedRun = nr;
            // Clear current run state so the canvas re-renders with the new output
            if (context && context.setPage) {
              context.setPage("playground");
            }
          }
        },
      });

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
