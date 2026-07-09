// Modal Studio — Legacy Wrapper
//
// Loads old testing-*.js modules through a shared contract.
// Preserves draft/setup state, preview state, experiment id,
// callbacks needed by old modules, and the comfyApi reference.
// Provides cleanup via stopLegacyController to avoid duplicate
// polling loops when switching legacy tabs.

let currentLegacyController = null;

export function stopLegacyController() {
  if (!currentLegacyController) return;
  if (typeof currentLegacyController.stop === "function") currentLegacyController.stop();
  if (typeof currentLegacyController.destroy === "function") currentLegacyController.destroy();
  currentLegacyController = null;
}

function buildLegacyOptions(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  const options = { apiBase };

  // Pass through draft/setup state and callbacks for the setup tab
  if (context && context.draft) options.draft = context.draft;
  if (context && context.onDraftChange) options.onDraftChange = context.onDraftChange;
  if (context && context.onRun) options.onRun = context.onRun;
  if (context && context.previewState) options.previewState = context.previewState;
  if (context && context.experimentId) options.experimentId = context.experimentId;

  return options;
}

export async function mountLegacyTab(rootEl, legacyTab, context) {
  stopLegacyController();

  // Resolve old module based on the requested legacy tab
  const LEGACY_MODULES = {
    dashboard: "./testing-dashboard.js",
    setup: "./testing-setup.js",
    profiles: "./testing-profiles.js",
    results: "./testing-results.js",
    history: "./testing-history.js",
    settings: "./testing-settings.js",
  };

  const modulePath = LEGACY_MODULES[legacyTab];
  if (!modulePath) {
    rootEl.textContent = `Unknown legacy tab: ${legacyTab}`;
    return;
  }

  try {
    const mod = await import(modulePath);
    const renderFnName = `${legacyTab}_tab_render`;
    if (typeof mod[renderFnName] !== "function") {
      throw new Error(`Module ${modulePath} missing export ${renderFnName}`);
    }

    while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);

    // Use comfyApi from context instead of passing null
    const api = (context && context.comfyApi) || null;
    const options = buildLegacyOptions(context);

    const result = mod[renderFnName](rootEl, api, options);
    currentLegacyController = result || null;
  } catch (e) {
    rootEl.innerHTML = `<div class="comfymodal-studio-card"><p style="color:var(--color-danger)">Failed to load legacy module: ${e.message}</p></div>`;
  }
}
