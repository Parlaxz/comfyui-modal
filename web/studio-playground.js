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
  canRunExperiment,
  getExperimentDisabledReason,
  executeExperimentRun,
} from "./studio-experiment-mode.js";
import {
  getVisibleControlsForPreset,
  getPresetCapabilitySummary,
  getUnavailableControlReasons,
} from "./studio-preset-capabilities.js";
import { resolveRunImageUrl, hasRunImage, normalizeStudioRun } from "./studio-run-normalizer.js";
import { saveSelection, loadSelection, clearSelection } from "./studio-playground-state.js";

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

// ── Polling helper for experiment status ──────────────────────────────────
// Polls getStudioRunStatus and updates runState to reflect queued,
// running, completed, or error states.
//
// Completion requires real evidence: completed cell count > 0,
// an explicit experiment.completed event, or cell.completed events.
// Empty/unknown snapshots with no definition stay in waiting state.

function _startPolling(container, state, context, actions, runState) {
  const experimentId = runState.experimentId || runState.runId;
  if (!experimentId) return;
  const apiBase = (context && context.apiBase) || "/comfymodal";
  let pollTimer = setInterval(async () => {
    const data = await getStudioRunStatus(apiBase, experimentId);
    if (!data) return;

    // Server-level error response
    if (data.status && data.status !== "ok") {
      clearInterval(pollTimer);
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
        clearInterval(pollTimer);
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
      clearInterval(pollTimer);
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
        clearInterval(pollTimer);
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
  }, 3000);
  // Allow the timer to be cleaned up if the container is removed
  container._pollTimer = pollTimer;
}

// ── Effective Controls builder ────────────────────────────────────────────
//
// Composes the full set of rendered bound controls from:
//   1. current user edits (state.playground.controls)
//   2. hydrated values (from latest completed run or snapshot defaults)
//   3. preset defaults
// This ensures all visible bound fields are sent on submission,
// not only fields that had explicit input events.

function buildEffectiveControls(state, preset, currentFeatureId) {
  const presetDefaults = (preset && preset.defaults) || {};
  const userOverrides = (state.playground && state.playground.controls) || {};
  const hydratedValues = (state.playground && state.playground._hydratedControls) || {};
  const visibleIds = getVisibleControlsForPreset(preset, currentFeatureId);
  const controls = {};
  visibleIds.forEach(function (ctrlId) {
    // Priority: user override > hydrated value > preset default
    if (ctrlId in userOverrides) {
      controls[ctrlId] = userOverrides[ctrlId];
    } else if (ctrlId in hydratedValues) {
      controls[ctrlId] = hydratedValues[ctrlId];
    } else if (ctrlId in presetDefaults) {
      controls[ctrlId] = presetDefaults[ctrlId];
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
// restore latest completed run or snapshot defaults.

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
    // Invalid/deleted preset — clear saved selection
    if (targetPresetId) {
      clearSelection();
    }
    targetPresetId = "";
    if (state.playground) {
      state.playground.selectedBackendId = "";
    }
  } else {
    if (state.playground) {
      state.playground.selectedBackendId = targetPresetId;
    }
  }

  // 6. If we have a valid preset, try to restore latest completed run
  if (targetPresetId) {
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
        // Pre-populate hydrated controls from the completed run's resolved/requested controls
        const hydratedCtrls = {};
        const srcControls = latest.resolvedControls || latest.requestedControls || {};
        Object.keys(srcControls).forEach(function (k) {
          hydratedCtrls[k] = srcControls[k];
        });
        state.playground._hydratedControls = hydratedCtrls;
        // Set defaults for any controls not in hydrated
        const preset = presets.find(function (p) { return (p.id || p.label || "") === targetPresetId; });
        if (preset && preset.defaults) {
          Object.keys(preset.defaults).forEach(function (k) {
            if (!(k in hydratedCtrls)) {
              hydratedCtrls[k] = preset.defaults[k];
            }
          });
        }
      }
    }
  }

  // 7. Persist the resolved selection
  if (targetPresetId) {
    saveSelection(targetPresetId, featureId);
  }
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

      const isBound = summary.requiredBindings.some((r) => r.key === ctrlId && r.bound)
        || summary.optionalBindings.some((o) => o.key === ctrlId && o.bound);

      // Check if this control is in the preset's nodeBindings
      const hasBinding = !!(preset.nodeBindings && preset.nodeBindings[ctrlId] && preset.nodeBindings[ctrlId].nodeId);

      const controlRow = renderControl(def, state, actions, preset);

      // Disable the control if it's a required binding not yet bound
      if (!isBound && !hasBinding) {
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
  panel.appendChild(renderRunButton(state, context, actions, isExperiment));

  return panel;
}

// ── Actions builder ──────────────────────────────────────────────────────

function buildActions(state, context) {
  return {
    setFeature(featureId) {
      state.playground.featureId = featureId;
      // Clear stale controls when feature changes
      state.playground.controls = {};
      state.playground._hydratedControls = {};
      state.playground._selectedRun = null;
      // Clear stale run state so Run button re-enables
      if (state.playground) state.playground.runState = null;
      // Persist selection
      saveSelection(state.playground.selectedBackendId, featureId);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    setBackend(backendId) {
      state.playground.selectedBackendId = backendId;
      // Clear stale controls when preset changes to avoid sending
      // controls that the new preset doesn't support
      state.playground.controls = {};
      state.playground._hydratedControls = {};
      state.playground._selectedRun = null;
      // Clear stale run state so Run button re-enables
      if (state.playground) state.playground.runState = null;
      // Persist selection
      saveSelection(backendId, state.playground.featureId);
      if (context && context.setPage) {
        context.setPage("playground");
      }
    },
    setControl(ctrlId, value) {
      if (!state.playground.controls) state.playground.controls = {};
      state.playground.controls[ctrlId] = value;
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
    toggleExperimentAxis(ctrlId, enabled) {
      if (!state.playground.experimentAxes) state.playground.experimentAxes = {};
      if (enabled) {
        const presetDefaults = (state.playground._currentPreset && state.playground._currentPreset.defaults) || {};
        const defaultValue = presetDefaults[ctrlId] ?? (CONTROL_DEFS[ctrlId] ? CONTROL_DEFS[ctrlId].defaultValue : "");
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
      const prevRunState = state.playground.runState;
      state.playground.runState = runState;
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
          if (experimentId && runs && runs.length > 0) {
            // Find the matching run by experiment ID
            var matched = runs.find(function (nr) {
              return nr.experimentId === experimentId;
            });
            if (!matched) {
              // Fallback: find by preset+feature
              matched = runs.find(function (nr) {
                return nr.presetId === state.playground.selectedBackendId &&
                       nr.featureId === (state.playground.featureId || "txt2img");
              });
            }
            if (matched) {
              state.playground._selectedRun = matched;
              if (matched.imageUrl) {
                state.playground.lastRunOutput = matched.imageUrl;
              }
              if (context && context.setPage) context.setPage("playground");
            }
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

function renderControl(def, state, actions, preset) {
  const presetDefaults = (preset && preset.defaults) || {};
  const currentOverrides = (state.playground && state.playground.controls) || {};
  const hydratedValues = (state.playground && state.playground._hydratedControls) || {};
  const value = currentOverrides[def.id] ?? hydratedValues[def.id] ?? presetDefaults[def.id] ?? def.defaultValue;
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

  if (input) group.appendChild(input);
  return group;
}

// ── Run Button ───────────────────────────────────────────────────────────

// ── Single-run submit helper ──────────────────────────────────────────────
//
// Immediately submits a single run using visible controls.
// Deduplicated from the inline handler in renderRunButton so that
// completed/error state can re-submit in a single click.

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

  if (actions && actions.setRunState) {
    actions.setRunState({ status: "running" });
  }

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
}

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
    // Terminal error state: show "Run" to let user retry immediately
    btn.disabled = false;
    btn.textContent = "Run";
    btn.title = "Run failed. Click to try again.";
    reason.appendChild(el("p", {
      text: runState.message || "Run failed. Try again.",
      style: "font-size:var(--font-size-sm);color:var(--color-danger);margin:4px 0 0;",
    }));
    // Single click: immediately submit using visible settings
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

        // Send all rendered bound fields — hydrated/restored values + current edits
        const controls = buildEffectiveControls(state, preset, currentFeatureId);

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
          // Refresh recent runs after successful submission will happen
          // in the polling completion handler via setRunState
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

// ── Right Workspace ──────────────────────────────────────────────────────

function renderWorkspace(state, context) {
  const workspace = el("div", { class: "comfymodal-studio-workspace", "data-testid": "workspace" });

  // Feature tabs
  workspace.appendChild(renderFeatureTabs(state, context));

  // Canvas area
  workspace.appendChild(renderCanvas(state, context));

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
  } else if (outputUrl) {
    const img = el("img", {
      src: outputUrl,
      style: "max-width:100%;max-height:100%;object-fit:contain;border-radius:4px;",
      "data-testid": "canvas-output",
    });
    canvas.appendChild(img);
  } else {
    canvas.appendChild(el("p", {
      text: "Generated output will appear here.",
      style: "color:var(--color-text-muted);",
    }));
  }

  return canvas;
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

  // ── Key generation settings ────────────────────────────────────────
  const settingsRow = el("div", { class: "comfymodal-studio-metadata-settings" });
  const genSettings = [];

  const seed = rc.seed || rqc.seed || "";
  if (seed) genSettings.push({ label: "Seed", value: String(seed) });
  if (rc.steps) genSettings.push({ label: "Steps", value: String(rc.steps) });
  if (rc.cfg || rc.guidance) genSettings.push({ label: "CFG", value: String(rc.cfg || rc.guidance) });
  if (rc.sampler_name || rc.sampler) genSettings.push({ label: "Sampler", value: String(rc.sampler_name || rc.sampler) });
  if (rc.scheduler) genSettings.push({ label: "Scheduler", value: String(rc.scheduler) });
  if (rc.denoise) genSettings.push({ label: "Denoise", value: String(rc.denoise) });
  if (rc.width && rc.height) genSettings.push({ label: "Size", value: rc.width + "\u00d7" + rc.height });
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

  // Full timings
  if (nr.durationMs) advancedItems.push({ label: "Duration (ms)", value: String(nr.durationMs) });
  if (Object.keys(nr.timings).length > 0) {
    advancedItems.push({ label: "Timings", value: JSON.stringify(nr.timings) });
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
      el("span", { text: item.value.substring(0, 200) + (item.value.length > 200 ? "\u2026" : "") }),
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

      const thumb = el("div", {
        class: "comfymodal-studio-carousel-item"
          + (nr.status === "completed" || nr.status === "success" || nr.status === "done" ? " completed" : "")
          + (nr.status === "error" || nr.status === "failed" ? " failed" : ""),
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
