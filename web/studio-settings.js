// Modal Studio — Settings
//
// Settings sections: Studio, Backends, Modal/Runtime, Features, Legacy.
// Legacy items are clickable and load old testing-*.js screens via
// the studio-legacy wrapper embedded inline.

export function renderSettings(state, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-settings";

  // If a legacy tab is active, render the legacy wrapper view
  if (state.settings.activeLegacyTab) {
    const legacyWrapper = renderLegacyView(state, context);
    container.appendChild(legacyWrapper);
    return container;
  }

  // Normal settings sections
  const sectionsHtml = `
    <div class="comfymodal-studio-settings-section" data-section="studio">
      <h3>Studio</h3>
      <p>Studio preferences — theme, default page, and workspace layout options.</p>
    </div>
    <div class="comfymodal-studio-settings-section" data-section="backends">
      <h3>Backends / Presets</h3>
      <p>Manage backend connections, profiles, and preset configurations.</p>
    </div>
    <div class="comfymodal-studio-settings-section" data-section="runtime">
      <h3>Modal / Runtime</h3>
      <p>Runtime settings — container limits, concurrency, and timeout preferences.</p>
    </div>
    <div class="comfymodal-studio-settings-section" data-section="features">
      <h3>Features</h3>
      <p>Configure Studio feature availability and defaults.</p>
    </div>
    <div class="comfymodal-studio-settings-section" data-section="legacy">
      <h3>Legacy</h3>
      <p>Load original testing-suite screens. Click a legacy tab to open it inside the Studio body.</p>
      <ul class="comfymodal-studio-legacy-list">
        <li data-legacy-tab="dashboard" class="comfymodal-studio-legacy-item">Legacy Dashboard</li>
        <li data-legacy-tab="setup" class="comfymodal-studio-legacy-item">Legacy Setup</li>
        <li data-legacy-tab="profiles" class="comfymodal-studio-legacy-item">Legacy Profiles</li>
        <li data-legacy-tab="results" class="comfymodal-studio-legacy-item">Legacy Results</li>
        <li data-legacy-tab="history" class="comfymodal-studio-legacy-item">Legacy History</li>
        <li data-legacy-tab="settings" class="comfymodal-studio-legacy-item">Legacy Settings</li>
      </ul>
    </div>
  `;
  container.innerHTML = sectionsHtml;

  // Wire up legacy item clicks to mount legacy tabs
  container.querySelectorAll("[data-legacy-tab]").forEach((item) => {
    item.addEventListener("click", () => {
      const tab = item.dataset.legacyTab;
      state.settings.activeLegacyTab = tab;
      // Re-render settings to show the legacy view
      while (container.firstChild) container.removeChild(container.firstChild);
      const newView = renderLegacyView(state, context);
      container.appendChild(newView);
    });
  });

  return container;
}

function renderLegacyView(state, context) {
  const wrapper = document.createElement("div");
  wrapper.className = "comfymodal-studio-legacy";

  // Back button to return to settings sections
  const backBtn = document.createElement("button");
  backBtn.className = "comfymodal-secondary-btn";
  backBtn.textContent = "← Back to Settings";
  backBtn.style.marginBottom = "var(--space-md)";
  backBtn.addEventListener("click", () => {
    state.settings.activeLegacyTab = "";
    // Signal shell to re-render (setPage triggers full re-render)
    if (context && context.setPage) {
      context.setPage("settings");
    }
  });
  wrapper.appendChild(backBtn);

  // Container for the legacy tab content
  const legacyBody = document.createElement("div");
  legacyBody.className = "comfymodal-studio-legacy-body";
  wrapper.appendChild(legacyBody);

  // Mount the requested legacy tab via the legacy wrapper
  if (context && context.mountLegacyTab) {
    context.mountLegacyTab(legacyBody, state.settings.activeLegacyTab, context);
  } else {
    legacyBody.innerHTML =
      '<div class="comfymodal-studio-card"><p>Legacy wrapper not available.</p></div>';
  }

  return wrapper;
}
