// Modal Studio — Studio-specific styles
//
// Adds Studio shell styling on top of existing testing-styles.js tokens.

const STUDIO_STYLE_ID = "comfymodal-studio-styles";

const STUDIO_CSS = `
/* ── Studio Override: use existing overlay modal but with Studio header ── */

.comfymodal-studio-modal {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  width: 1200px;
  height: 780px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
}

.comfymodal-studio-header {
  display: flex;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--color-border-default);
  flex-shrink: 0;
  background: var(--color-bg-toolbar);
}

.comfymodal-studio-header h2 {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  flex: 1;
  color: var(--color-text-primary);
  letter-spacing: 0.01em;
}

.comfymodal-studio-topnav {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-border-default);
  flex-shrink: 0;
  padding: 0 var(--space-md);
  background: var(--color-bg-base);
  min-height: var(--tab-height);
}

.comfymodal-studio-topnav button {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  padding: 10px 16px;
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border-bottom: 2px solid transparent;
  transition: color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard);
}

.comfymodal-studio-topnav button:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.comfymodal-studio-topnav button.active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
  font-weight: var(--font-weight-semibold);
}

.comfymodal-studio-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: var(--space-lg);
  background: var(--color-bg-base);
}

/* ── Playground ──────────────────────────────────────────── */

.comfymodal-studio-playground {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  height: 100%;
}

.comfymodal-studio-control-panel {
  width: 340px;
  flex-shrink: 0;
}

.comfymodal-studio-workspace {
  flex: 1;
  min-width: 0;
}

.comfymodal-studio-canvas {
  min-height: 300px;
  border: 1px dashed var(--color-border-default);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.comfymodal-studio-filmstrip {
  display: flex;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
}

.comfymodal-studio-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
}

/* ── Axis popover ────────────────────────────────────────── */

.comfymodal-studio-axis-popover {
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}

/* ── History ─────────────────────────────────────────────── */

.comfymodal-studio-history {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── Settings ────────────────────────────────────────────── */

.comfymodal-studio-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.comfymodal-studio-settings-section {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
}

.comfymodal-studio-settings-section h3 {
  margin: 0 0 var(--space-sm);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.comfymodal-studio-settings-section p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.comfymodal-studio-legacy-list {
  list-style: none;
  margin: var(--space-sm) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.comfymodal-studio-legacy-list li {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-studio-legacy-list li:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

/* ── Legacy wrapper ──────────────────────────────────────── */

.comfymodal-studio-legacy {
  height: 100%;
  overflow-y: auto;
}

/* ── Playground ──────────────────────────────────────────── */

.comfymodal-studio-playground {
  display: flex;
  flex-direction: row;
  gap: var(--space-lg);
  height: 100%;
  overflow: hidden;
}

.comfymodal-studio-control-panel {
  width: 340px;
  min-width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
  padding-right: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.comfymodal-studio-workspace {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  overflow-y: auto;
}

/* ── Control Groups ──────────────────────────────────────── */

.comfymodal-studio-control-group {
  margin-bottom: var(--space-sm);
}

.comfymodal-studio-control-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: 2px;
}

.comfymodal-studio-control-help {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-bottom: 2px;
}

.comfymodal-studio-textarea {
  width: 100%;
  min-height: 60px;
  resize: vertical;
  box-sizing: border-box;
}

.comfymodal-studio-number-input {
  width: 100%;
  box-sizing: border-box;
}

.comfymodal-studio-select {
  width: 100%;
  box-sizing: border-box;
}

.comfymodal-studio-control-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-style: italic;
}

/* ── Mask Controls ───────────────────────────────────────── */

.comfymodal-studio-mask-controls {
  border-top: 1px solid var(--color-border-default);
  margin-top: var(--space-sm);
  padding-top: var(--space-sm);
}

.comfymodal-studio-section-heading {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  margin: var(--space-md) 0 var(--space-xs);
}

/* ── Feature Tabs ────────────────────────────────────────── */

.comfymodal-studio-feature-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-border-default);
  flex-shrink: 0;
}

.comfymodal-studio-feature-tab {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  padding: 8px 16px;
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border-bottom: 2px solid transparent;
  transition: color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}

.comfymodal-studio-feature-tab:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.comfymodal-studio-feature-tab.active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
}

/* ── Placeholder notices ─────────────────────────────────── */

.comfymodal-studio-placeholder-notice {
  background: var(--color-bg-surface);
  border: 1px dashed var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  text-align: center;
}

.comfymodal-studio-placeholder-notice p {
  margin: var(--space-sm) 0;
}

/* ── Disabled states ─────────────────────────────────────── */

.comfymodal-studio-disabled-reason {
  margin-top: var(--space-xs);
}

.comfymodal-studio-disabled-reason p {
  display: inline;
}

.comfymodal-studio-empty-state {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

/* ── Run section ─────────────────────────────────────────── */

.comfymodal-studio-run-section {
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px solid var(--color-border-default);
}

.comfymodal-studio-run-section .comfymodal-primary-btn {
  width: 100%;
}

/* ── Backend Selector ────────────────────────────────────── */

.comfymodal-studio-backend-selector {
  margin-bottom: var(--space-sm);
}

/* ── Experiment Mode ─────────────────────────────────────── */

.comfymodal-studio-experiment-toggle {
  margin-bottom: var(--space-sm);
}

.comfymodal-studio-experiment-toggle button {
  width: 100%;
}

.comfymodal-studio-experiment-active {
  background: var(--color-warning-bg);
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.comfymodal-studio-experiment-mode {
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  margin-bottom: var(--space-md);
}

.comfymodal-studio-block-heading {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-xs);
}

.comfymodal-studio-compare-backends {
  margin-bottom: var(--space-md);
}

.comfymodal-studio-compare-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.comfymodal-studio-matrix-summary {
  margin-bottom: var(--space-md);
}

.comfymodal-studio-matrix-body {
  font-size: var(--font-size-sm);
}

.comfymodal-studio-matrix-axis-list {
  list-style: none;
  padding: 0;
  margin: var(--space-xs) 0;
}

.comfymodal-studio-matrix-axis-list li {
  padding: 2px 0;
  color: var(--color-text-secondary);
}

.comfymodal-studio-matrix-total {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-top: var(--space-xs);
}

/* ── Axis Checkbox ───────────────────────────────────────── */

.comfymodal-studio-axis-checkbox-wrapper {
  display: inline-flex;
  align-items: center;
  margin-right: 4px;
}

.comfymodal-studio-axis-checkbox {
  cursor: pointer;
  accent-color: var(--color-accent);
}

/* ── Canvas ──────────────────────────────────────────────── */

.comfymodal-studio-canvas {
  min-height: 300px;
  border: 1px dashed var(--color-border-default);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  flex: 1;
}

/* ── Filmstrip ───────────────────────────────────────────── */

.comfymodal-studio-filmstrip {
  display: flex;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  min-height: 40px;
  align-items: center;
}
`;

let _injected = false;

export function ensureStudioStyles() {
  if (_injected) return;
  if (document.getElementById(STUDIO_STYLE_ID)) {
    _injected = true;
    return;
  }
  const style = document.createElement("style");
  style.id = STUDIO_STYLE_ID;
  style.textContent = STUDIO_CSS;
  document.head.appendChild(style);
  _injected = true;
}
