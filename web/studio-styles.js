// Modal Studio — Studio-specific styles
//
// Adds Studio shell styling on top of existing testing-styles.js tokens.

const STUDIO_STYLE_ID = "comfymodal-studio-styles";

const STUDIO_CSS = `
/* ── Studio Override: larger modal with dark Nexus-style chrome ── */

.comfymodal-studio-modal {
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  width: min(98vw, 1760px);
  height: min(94vh, 1040px);
  max-width: calc(100vw - 16px);
  max-height: calc(100vh - 16px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: #d0d0d0;
  font-size: 13px;
}

/* When modal is open, body should not scroll behind it */
body.comfymodal-body-scroll-lock {
  overflow: hidden;
}

.comfymodal-studio-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.comfymodal-studio-header {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
  background: #0a0a0a;
  min-height: 40px;
}

.comfymodal-studio-header h2 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  flex: 1;
  color: #e0e0e0;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.comfymodal-studio-topnav {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
  padding: 0 8px;
  background: #0d0d0d;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

@media (max-width: 480px) {
  .comfymodal-studio-topnav button {
    padding: 10px 10px;
    min-height: 44px;
    white-space: nowrap;
  }

  /* Close button — expand hit area to 44px via padding */
  .comfymodal-testing-close {
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Feature tabs — ensure minimum tap height */
  .comfymodal-studio-feature-tab {
    min-height: 44px;
    padding-top: 10px;
    padding-bottom: 10px;
  }

  /* Primary / secondary / destructive buttons */
  .comfymodal-primary-btn,
  .comfymodal-secondary-btn,
  .comfymodal-destructive-btn,
  .comfymodal-studio-reset-link {
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Inputs, selects, number inputs */
  .comfymodal-studio-number-input,
  .comfymodal-studio-select,
  .comfymodal-input,
  .comfymodal-testing-input {
    min-height: 44px;
  }

  /* Preview overlay close button */
  .comfymodal-studio-preview-overlay-close {
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Favorite star — expand hit area to 44px without growing the icon */
  .comfymodal-studio-favorite-star {
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
}

.comfymodal-studio-topnav button {
  background: transparent;
  border: none;
  color: #666;
  padding: 8px 14px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}

.comfymodal-studio-topnav button:hover {
  color: #d0d0d0;
  background: #1a1a1a;
}

.comfymodal-studio-topnav button.active {
  color: var(--color-accent, #5a7fdb);
  border-bottom-color: var(--color-accent, #5a7fdb);
}

/* ── Shell page container ────────────────────────────────── */

.comfymodal-studio-pagecontainer {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  padding: 16px;
  background: #0d0d0d;
  /* Prevent scroll trap: ensure this is the ONLY scrollable container at this level */
  max-height: 100%;
}

.comfymodal-studio-pagecontainer::-webkit-scrollbar {
  width: 6px;
}
.comfymodal-studio-pagecontainer::-webkit-scrollbar-track {
  background: transparent;
}
.comfymodal-studio-pagecontainer::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 3px;
}
.comfymodal-studio-pagecontainer::-webkit-scrollbar-thumb:hover {
  background: #444;
}

/* ── Playground ──────────────────────────────────────────── */

.comfymodal-studio-playground {
  display: flex;
  flex-direction: row;
  gap: 0;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.comfymodal-studio-control-panel {
  width: 400px;
  min-width: 200px;
  flex-shrink: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 100%;
}

.comfymodal-studio-workspace {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  max-height: 100%;
}

.comfymodal-studio-resize-handle {
  width: 12px;
  cursor: col-resize;
  flex-shrink: 0;
  touch-action: none;
  position: relative;
  background: transparent;
  user-select: none;
}

.comfymodal-studio-resize-handle::before {
  content: '';
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 50%;
  transform: translateX(-50%);
  width: 2px;
  background: #2a2a2a;
  border-radius: 1px;
  transition: background 0.15s;
}

.comfymodal-studio-resize-handle:hover::before,
.comfymodal-studio-resize-handle.active::before {
  background: var(--color-accent, #5a7fdb);
}

/* ── Control Groups ──────────────────────────────────────── */

.comfymodal-studio-control-group {
  margin-bottom: 4px;
}

.comfymodal-studio-control-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  color: #a0a0a0;
  margin-bottom: 2px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.comfymodal-studio-control-help {
  font-size: 11px;
  color: #555;
  margin-bottom: 2px;
}

.comfymodal-studio-textarea {
  width: 100%;
  min-height: 60px;
  resize: vertical;
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 6px 8px;
  font-size: 12px;
  border-radius: 3px;
}

.comfymodal-studio-textarea:focus {
  border-color: var(--color-border-focus, #5a7fdb);
  outline: none;
}

/* ── Prompt textarea (primary input treatment) ──────────── */

.comfymodal-studio-prompt-textarea {
  min-height: 100px;
  font-size: 13px;
  line-height: 1.5;
  padding: 10px 12px;
  background: #0d0d0d;
  border-color: #3a3a3a;
  transition: border-color 0.15s, box-shadow 0.15s;
  resize: vertical;
}
.comfymodal-studio-prompt-textarea:focus {
  border-color: var(--color-accent, #5a7fdb);
  box-shadow: 0 0 0 1px rgba(90, 127, 219, 0.2);
  background: #111;
}

.comfymodal-studio-prompt-textarea.negative {
  min-height: 80px;
  font-size: 12px;
  border-color: #3a2a2a;
}
.comfymodal-studio-prompt-textarea.negative:focus {
  border-color: #ef4444;
  box-shadow: 0 0 0 1px rgba(239, 68, 68, 0.15);
}

.comfymodal-studio-number-input:focus {
  border-color: var(--color-border-focus, #5a7fdb);
  outline: none;
}

.comfymodal-studio-number-input {
  width: 100%;
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 5px 8px;
  font-size: 12px;
  border-radius: 3px;
}

.comfymodal-studio-number-input:focus {
  border-color: var(--color-border-focus, #5a7fdb);
  outline: none;
}

.comfymodal-studio-select {
  width: 100%;
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 5px 8px;
  font-size: 12px;
  border-radius: 3px;
}

.comfymodal-studio-control-note {
  font-size: 11px;
  color: #555;
  font-style: italic;
}

/* ── Mask Controls ───────────────────────────────────────── */

.comfymodal-studio-mask-controls {
  border-top: 1px solid #2a2a2a;
  margin-top: 4px;
  padding-top: 4px;
}

.comfymodal-studio-section-heading {
  font-size: 11px;
  font-weight: 600;
  color: #888;
  margin: 8px 0 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Feature Tabs ────────────────────────────────────────── */

.comfymodal-studio-feature-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
  background: #0d0d0d;
}

.comfymodal-studio-feature-tab {
  background: transparent;
  border: none;
  color: #555;
  padding: 6px 14px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, background 0.15s;
}

.comfymodal-studio-feature-tab:hover {
  color: #d0d0d0;
  background: #1a1a1a;
}

.comfymodal-studio-feature-tab.active {
  color: var(--color-accent, #5a7fdb);
  border-bottom-color: var(--color-accent, #5a7fdb);
}

/* ── Placeholder notices ─────────────────────────────────── */

.comfymodal-studio-placeholder-notice {
  background: #111;
  border: 1px dashed #2a2a2a;
  border-radius: 4px;
  padding: 16px;
  text-align: center;
}

.comfymodal-studio-placeholder-notice p {
  margin: 4px 0;
}

/* ── Disabled states ─────────────────────────────────────── */

.comfymodal-studio-disabled-reason {
  margin-top: 4px;
}

.comfymodal-studio-disabled-reason p {
  display: inline;
}

.comfymodal-studio-empty-state {
  color: #555;
  font-size: 12px;
}

/* ── Info Hint / Tooltip ─────────────────────────────────── */

.comfymodal-studio-info-hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  font-size: 12px;
  color: #555;
  cursor: help;
  position: relative;
  flex-shrink: 0;
}

.comfymodal-studio-info-hint:hover {
  color: #888;
}

.comfymodal-studio-tooltip {
  display: none;
  position: absolute;
  bottom: calc(100% + 4px);
  left: 50%;
  transform: translateX(-50%);
  background: #1a1a1a;
  border: 1px solid #333;
  color: #ccc;
  padding: 6px 10px;
  font-size: 11px;
  border-radius: 3px;
  white-space: normal;
  max-width: 240px;
  min-width: 120px;
  z-index: 1000;
  line-height: 1.4;
  pointer-events: none;
  text-transform: none;
  letter-spacing: normal;
  font-weight: 400;
}

.comfymodal-studio-info-hint:focus .comfymodal-studio-tooltip,
.comfymodal-studio-info-hint:hover .comfymodal-studio-tooltip {
  display: block;
}

/* ── Run section ─────────────────────────────────────────── */

.comfymodal-studio-run-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #2a2a2a;
}

/* ── Primary button (red) ────────────────────────────────── */

.comfymodal-studio-run-section .comfymodal-primary-btn,
.comfymodal-primary-btn {
  background: var(--color-accent, #5a7fdb);
  color: #fff;
  border: none;
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-radius: 3px;
  cursor: pointer;
  width: 100%;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.comfymodal-primary-btn:hover:not(:disabled) {
  background: var(--color-accent-hover, #6a8ceb);
}

.comfymodal-primary-btn:disabled {
  background: #333;
  color: #555;
  cursor: not-allowed;
}

/* ── Secondary / Destructive buttons ─────────────────────── */

.comfymodal-secondary-btn {
  background: #1a1a1a;
  color: #aaa;
  border: 1px solid #333;
  padding: 5px 12px;
  font-size: 11px;
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.comfymodal-secondary-btn:hover {
  background: #222;
  color: #d0d0d0;
}

.comfymodal-destructive-btn {
  background: var(--color-danger-bg, #1a0000);
  color: var(--color-danger, #dc2626);
  border: 1px solid var(--color-border-danger, #ef4444);
  padding: 5px 12px;
  font-size: 11px;
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.comfymodal-destructive-btn:hover {
  background: #2a0000;
}

/* ── Backend Selector ────────────────────────────────────── */

.comfymodal-studio-backend-selector {
  margin-bottom: 4px;
}

/* ── Experiment Mode ─────────────────────────────────────── */

.comfymodal-studio-experiment-toggle {
  margin-bottom: 4px;
}

.comfymodal-studio-experiment-toggle button {
  width: 100%;
}

.comfymodal-studio-experiment-active {
  background: var(--color-accent, #5a7fdb) !important;
  border-color: var(--color-accent, #5a7fdb) !important;
  color: #fff !important;
}

.comfymodal-studio-experiment-mode {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 12px;
}

.comfymodal-studio-block-heading {
  font-size: 11px;
  font-weight: 600;
  color: #a0a0a0;
  margin: 0 0 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.comfymodal-studio-compare-backends {
  margin-bottom: 12px;
}

.comfymodal-studio-compare-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* ── Collapsible group sections ───────────────────────── */

.comfymodal-studio-collapsible-summary {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 8px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
  font-weight: 600;
  color: #a0a0a0;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  transition: background 0.15s, color 0.15s;
  width: 100%;
  font-family: inherit;
  line-height: inherit;
  text-align: left;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.comfymodal-studio-collapsible-summary:hover {
  background: #1a1a1a;
  color: #d0d0d0;
}
.comfymodal-studio-collapsible-summary:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 1px;
}
.comfymodal-studio-collapsible-summary .arrow {
  font-size: 8px;
  transition: transform 0.2s;
  flex-shrink: 0;
}
.comfymodal-studio-collapsible-summary[aria-expanded="true"] .arrow {
  transform: rotate(90deg);
}
.comfymodal-studio-collapsible-content {
  display: none;
  padding: 4px 0 4px 12px;
  border-left: 1px solid #2a2a2a;
  margin-left: 8px;
}
.comfymodal-studio-collapsible-content.is-visible {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.comfymodal-studio-collapsible-content.is-visible > .comfymodal-studio-collapsible-content {
  margin-left: 0;
  border-left: none;
}

/* ── Compare preset item ─────────────────────────────── */

.comfymodal-studio-compare-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  font-size: 11px;
}
.comfymodal-studio-compare-checkbox {
  accent-color: var(--color-accent, #5a7fdb);
  cursor: pointer;
  flex-shrink: 0;
}
.comfymodal-studio-compare-item label {
  cursor: pointer;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Backend group section ───────────────────────────── */

.comfymodal-studio-backend-group-heading {
  font-size: 10px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 6px 8px 2px;
  margin: 0;
}
.comfymodal-studio-backend-group-section {
  margin-bottom: 4px;
}

.comfymodal-studio-matrix-summary {
  margin-bottom: 12px;
}

.comfymodal-studio-matrix-body {
  font-size: 12px;
}

.comfymodal-studio-matrix-axis-list {
  list-style: none;
  padding: 0;
  margin: 4px 0;
}

.comfymodal-studio-matrix-axis-list li {
  padding: 2px 0;
  color: #888;
}

.comfymodal-studio-matrix-total {
  font-weight: 600;
  color: #d0d0d0;
  margin-top: 4px;
}

.comfymodal-studio-matrix-warning {
  font-size: 11px;
  margin-top: 4px;
}

/* ── Axis Checkbox ───────────────────────────────────────── */

.comfymodal-studio-axis-checkbox-wrapper {
  display: inline-flex;
  align-items: center;
  margin-right: 4px;
}

.comfymodal-studio-axis-checkbox {
  cursor: pointer;
  accent-color: var(--color-accent, #5a7fdb);
}

/* ── Axis Editor ─────────────────────────────────────────── */

.comfymodal-studio-axis-editor {
  margin: 4px 0 8px;
  padding-left: 20px;
}

.comfymodal-studio-axis-editor-values {
}

.comfymodal-studio-axis-editor-values textarea,
.comfymodal-studio-axis-editor-values input[type="text"] {
  width: 100%;
  box-sizing: border-box;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 4px 6px;
  font-size: 11px;
  border-radius: 2px;
}

.comfymodal-studio-axis-editor-values textarea:focus,
.comfymodal-studio-axis-editor-values input[type="text"]:focus {
  border-color: var(--color-border-focus, #5a7fdb);
  outline: none;
}

/* ── Running Config Panel (inline in control panel) ──────── */
/* Renders inside the left control panel, below the experiment */
/* mode controls.  Uses flex column layout so the prompt       */
/* section stretches to fill min-height.  Translucent surface. */

.comfymodal-studio-running-config {
  margin-bottom: 8px;
  min-height: 360px;
  background: rgba(12, 12, 12, 0.88);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border: 1px solid rgba(40, 40, 40, 0.7);
  border-radius: 4px;
  padding: 7px 10px;
  display: none;
  flex-direction: column;
  box-sizing: border-box;
}

.comfymodal-studio-running-config.is-visible {
  display: flex;
}

/* ── Header (fixed) ─────────────────────────────────────── */

.comfymodal-studio-running-config-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  flex-shrink: 0;
}

.comfymodal-studio-running-config-title {
  font-weight: 600;
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #a0a0a0;
  flex-shrink: 0;
}

.comfymodal-studio-running-config-preset {
  font-size: 8px;
  color: #777;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: rgba(26, 26, 26, 0.8);
  padding: 1px 5px;
  border-radius: 2px;
}

/* ── Prompt section (flex-grows to fill remaining height) ─ */

.comfymodal-studio-running-config-prompt {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-bottom: 3px;
  padding-bottom: 3px;
  border-bottom: 1px solid rgba(26, 26, 26, 0.7);
}

.comfymodal-studio-running-config-label {
  font-size: 8px;
  color: #777;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  display: block;
  flex-shrink: 0;
}

.comfymodal-studio-running-config-prompt-text {
  font-size: 10px;
  color: #d0d0d0;
  word-wrap: break-word;
  display: block;
  margin-top: 1px;
  line-height: 1.4;
  /* Fill remaining space in the prompt container — no max-height clamp */
}

/* ── Parameter grid (fixed summary row) ─────────────────── */

.comfymodal-studio-running-config-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1px 6px;
  margin-bottom: 3px;
  padding-bottom: 3px;
  border-bottom: 1px solid rgba(26, 26, 26, 0.7);
  flex-shrink: 0;
}

.comfymodal-studio-running-config-item {
  display: inline-flex;
  gap: 2px;
  font-size: 9px;
  line-height: 1.6;
}

.comfymodal-studio-running-config-item .comfymodal-studio-running-config-label {
  font-size: 9px;
  color: #888;
  text-transform: none;
  letter-spacing: normal;
  display: inline;
  white-space: nowrap;
}

.comfymodal-studio-running-config-item .comfymodal-studio-running-config-value {
  font-size: 9px;
  color: #ccc;
  white-space: nowrap;
}

/* ── Experiment axes section (fixed) ────────────────────── */

.comfymodal-studio-running-config-axes {
  flex-shrink: 0;
  margin-top: 3px;
  padding-top: 3px;
  border-top: 1px solid rgba(26, 26, 26, 0.7);
}

.comfymodal-studio-running-config-axes-title {
  font-size: 8px;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 1px;
  display: block;
}

.comfymodal-studio-running-config-axes-list {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
}

.comfymodal-studio-running-config-axis-item {
  font-size: 8px;
  color: #999;
  background: rgba(26, 26, 26, 0.7);
  padding: 1px 5px;
  border-radius: 2px;
  white-space: nowrap;
}

/* ── Preset count (fixed footer) ────────────────────────── */

.comfymodal-studio-running-config-preset-count {
  flex-shrink: 0;
  margin-top: 3px;
  font-size: 8px;
  color: #777;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Canvas (dotted grid background) ─────────────────────── */

.comfymodal-studio-canvas {
  position: relative;
  min-height: 300px;
  border: 1px dashed #2a2a2a;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  flex: 1;
  background-image:
    radial-gradient(circle, #2a2a2a 1px, transparent 1px);
  background-size: 20px 20px;
}

.comfymodal-studio-live-return {
  position: absolute;
  right: 8px;
  bottom: 8px;
  left: 8px;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.82);
}

.comfymodal-studio-live-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #aaa;
  font-size: 10px;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.comfymodal-studio-live-indicator::before {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4ade80;
  content: "";
}

.comfymodal-studio-live-return-btn {
  flex-shrink: 0;
  padding: 3px 8px;
  border: 1px solid #444;
  border-radius: 3px;
  background: transparent;
  color: #aaa;
  cursor: pointer;
  font-family: inherit;
  font-size: 10px;
}

.comfymodal-studio-live-return-btn:hover,
.comfymodal-studio-live-return-btn:focus-visible {
  border-color: var(--color-accent, #5a7fdb);
  background: #2a2a2a;
  color: #fff;
}

.comfymodal-studio-live-return-btn:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

/* ── Carousel ───────────────────────────────────────────── */

.comfymodal-studio-carousel {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 60px;
}

.comfymodal-studio-carousel-track {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 0;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
}

.comfymodal-studio-carousel-track::-webkit-scrollbar {
  height: 4px;
}

.comfymodal-studio-carousel-track::-webkit-scrollbar-track {
  background: transparent;
}

.comfymodal-studio-carousel-track::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 2px;
}

.comfymodal-studio-carousel-item {
  flex-shrink: 0;
  width: 80px;
  height: 80px;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid #2a2a2a;
  position: relative;
  transition: border-color 0.15s, transform 0.15s;
  background: none;
  padding: 0;
  font-family: inherit;
  font-size: inherit;
  color: inherit;
  line-height: 1;
}

.comfymodal-studio-carousel-item:hover {
  border-color: var(--color-accent, #5a7fdb);
  transform: scale(1.05);
}

.comfymodal-studio-carousel-item:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

.comfymodal-studio-carousel-item.completed {
  border-color: #1a4a1a;
}

.comfymodal-studio-carousel-item.failed {
  border-color: #4a1a1a;
}

.comfymodal-studio-carousel-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.comfymodal-studio-carousel-status {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1px solid rgba(0,0,0,0.5);
}

/* ── Carousel Header & Actions ──────────────────────────── */

.comfymodal-studio-carousel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 24px;
}

.comfymodal-studio-carousel-header-label {
  font-size: 12px;
  color: #888;
}

.comfymodal-studio-carousel-actions {
  display: flex;
  gap: 4px;
}

.comfymodal-studio-carousel-btn {
  background: transparent;
  border: none;
  color: #666;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
  font-family: inherit;
  transition: color 0.15s;
}

.comfymodal-studio-carousel-btn:hover {
  color: #fff;
}

.comfymodal-studio-carousel-btn.danger:hover {
  color: #f87171;
}

.comfymodal-studio-carousel-btn.close-btn {
  font-size: 16px;
  padding: 2px 4px;
}

/* ── Carousel Reveal Bar ─────────────────────────────────── */

.comfymodal-studio-carousel-reveal {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px;
  border: 1px dashed #333;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  color: #666;
  background: transparent;
  width: 100%;
  font-family: inherit;
  transition: border-color 0.15s, color 0.15s;
}

.comfymodal-studio-carousel-reveal:hover {
  border-color: var(--color-accent, #5a7fdb);
  color: #ccc;
}

/* ── History ─────────────────────────────────────────────── */

.comfymodal-studio-history {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── History Gallery Grid ──────────────────────────────── */

.comfymodal-studio-history-gallery {
  display: grid;
  grid-template-columns: repeat(var(--columns, 6), 1fr);
  gap: 8px;
  margin-top: 8px;
}

.comfymodal-studio-history-column-select {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: #888;
  margin-left: auto;
}
.comfymodal-studio-history-column-select label {
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.comfymodal-studio-history-column-select input {
  width: 36px;
  font-size: 10px;
  padding: 2px 4px;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  border-radius: 2px;
  text-align: center;
  font-family: inherit;
}
.comfymodal-studio-history-column-select input:focus {
  border-color: var(--color-accent, #5a7fdb);
  outline: none;
}

.comfymodal-studio-history-card {
  position: relative;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.15s;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.comfymodal-studio-history-card:hover {
  border-color: var(--color-accent, #5a7fdb);
  transform: scale(1.03);
  z-index: 1;
}

.comfymodal-studio-history-card.completed {
  border-color: #1a4a1a;
}

.comfymodal-studio-history-card.failed {
  border-color: #4a1a1a;
}

.comfymodal-studio-history-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.comfymodal-studio-history-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px;
  color: #555;
  text-align: center;
  width: 100%;
  height: 100%;
}

.comfymodal-studio-history-fallback-icon {
  font-size: 24px;
  opacity: 0.5;
}

.comfymodal-studio-history-fallback-label {
  font-size: 10px;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.comfymodal-studio-history-card-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(transparent, rgba(0,0,0,0.85));
  padding: 20px 6px 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
}

.comfymodal-studio-history-card:hover .comfymodal-studio-history-card-overlay {
  opacity: 1;
}

.comfymodal-studio-history-card-status {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #4ade80;
}

.comfymodal-studio-history-card.completed .comfymodal-studio-history-card-status {
  color: #4ade80;
}

.comfymodal-studio-history-card.failed .comfymodal-studio-history-card-status {
  color: #f87171;
}

.comfymodal-studio-history-card-prompt {
  font-size: 9px;
  color: #aaa;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-history-card-time {
  font-size: 8px;
  color: #666;
}

/* ── History Preview Overlay / Lightbox ────────────────── */

/* ── Shared zoom wrap ──────────────────────────────────── */

.comfymodal-studio-zoom-wrap {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}
.comfymodal-studio-zoom-image-container {
  overflow: auto;
  position: relative;
  width: 100%;
  max-width: 100%;
  max-height: 80vh;
  display: flex;
  align-items: center;
  justify-content: center;
  touch-action: pan-x pan-y;
}
.comfymodal-studio-zoom-image-container img {
  max-width: 100%;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6);
  transition: transform 0.2s ease;
  transform-origin: center center;
  display: block;
}
.comfymodal-studio-zoom-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  background: rgba(0,0,0,0.7);
  border: 1px solid #333;
  border-radius: 4px;
  padding: 2px 4px;
}
.comfymodal-studio-zoom-btn {
  background: transparent;
  border: none;
  color: #ccc;
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
  border-radius: 2px;
  font-family: inherit;
  transition: color 0.15s, background 0.15s;
}
.comfymodal-studio-zoom-btn:hover {
  color: #fff;
  background: rgba(255,255,255,0.1);
}
.comfymodal-studio-zoom-btn:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 1px;
}
.comfymodal-studio-zoom-label {
  font-size: 10px;
  color: #888;
  min-width: 36px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  user-select: none;
}
.comfymodal-studio-zoom-btn.fit-active {
  color: var(--color-accent, #5a7fdb);
}
.comfymodal-studio-zoom-btn.fullscreen-active {
  color: var(--color-accent, #5a7fdb);
}

/* ── Shared Preview Overlay ─────────────────────────────── */

.comfymodal-studio-preview-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.comfymodal-studio-preview-overlay-backdrop {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
}
.comfymodal-studio-preview-overlay-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.comfymodal-studio-preview-overlay-close {
  position: absolute;
  top: -32px;
  right: 0;
  background: transparent;
  border: none;
  color: #aaa;
  font-size: 24px;
  cursor: pointer;
  padding: 4px 8px;
  line-height: 1;
  z-index: 1;
}
.comfymodal-studio-preview-overlay-close:hover {
  color: #fff;
}
.comfymodal-studio-preview-overlay-close:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}
.comfymodal-studio-preview-overlay-noimage {
  width: 240px;
  height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  color: #555;
  font-size: 12px;
}
.comfymodal-studio-preview-overlay-sections {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  width: 100%;
}

.comfymodal-studio-preview-info {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 11px;
  color: #aaa;
  max-width: 100%;
}

.comfymodal-studio-preview-status {
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 10px;
  color: #4ade80;
}

.comfymodal-studio-preview-prompt {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-preview-time {
  color: #666;
  flex-shrink: 0;
}

.comfymodal-studio-preview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  justify-content: center;
  margin-top: 4px;
}

.comfymodal-studio-preview-meta-item {
  font-size: 10px;
  color: #777;
}

/* ── Settings ────────────────────────────────────────────── */

.comfymodal-studio-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.comfymodal-studio-settings-section {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 16px;
}

.comfymodal-studio-settings-section h3 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: #d0d0d0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.comfymodal-studio-settings-section p {
  margin: 0;
  color: #888;
  font-size: 12px;
}

/* ── Backend page ────────────────────────────────────────── */

.comfymodal-studio-backend {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.comfymodal-studio-backend-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
  background: #0d0d0d;
}

.comfymodal-studio-backend-tab {
  background: transparent;
  border: none;
  color: #555;
  padding: 6px 14px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, background 0.15s;
}

.comfymodal-studio-backend-tab:hover {
  color: #d0d0d0;
  background: #1a1a1a;
}

.comfymodal-studio-backend-tab.active {
  color: var(--color-accent, #5a7fdb);
  border-bottom-color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-backend-body {
  flex: 1;
  display: flex;
  flex-direction: row;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}

.comfymodal-studio-backend-list {
  width: 280px;
  min-width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  max-height: 100%;
}

.comfymodal-studio-backend-detail {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  min-height: 0;
}

.comfymodal-studio-backend-card {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  padding: 10px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.comfymodal-studio-backend-card:hover {
  border-color: #444;
}

.comfymodal-studio-backend-card.active {
  border-color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-backend-card h4 {
  margin: 0 0 2px;
  font-size: 12px;
  font-weight: 600;
  color: #d0d0d0;
}

.comfymodal-studio-backend-card p {
  margin: 0;
  font-size: 11px;
  color: #555;
}

.comfymodal-studio-backend-detail-card {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  padding: 16px;
}

.comfymodal-studio-backend-field {
  margin-bottom: 8px;
}

.comfymodal-studio-backend-field label {
  display: block;
  font-size: 11px;
  color: #888;
  margin-bottom: 2px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.comfymodal-studio-backend-field input,
.comfymodal-studio-backend-field textarea,
.comfymodal-studio-backend-field select {
  width: 100%;
  box-sizing: border-box;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 5px 8px;
  font-size: 12px;
  border-radius: 2px;
}

.comfymodal-studio-backend-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
}

/* ── Responsive: breakpoint 768px ───────────────────────── */

@media (max-width: 768px) {
  .comfymodal-studio-playground {
    flex-direction: column;
  }
  .comfymodal-studio-control-panel {
    width: 100% !important;
    min-width: 0;
    max-height: 40vh;
    overflow-y: auto;
  }
  .comfymodal-studio-resize-handle {
    display: none;
  }
  .comfymodal-studio-backend-body {
    flex-direction: column;
  }
  .comfymodal-studio-backend-list {
    width: 100%;
    min-width: 0;
  }
  .comfymodal-studio-history-gallery {
    --columns: 3 !important;
    grid-template-columns: repeat(3, 1fr);
  }
  .comfymodal-studio-history-column-select {
    display: none;
  }
  .comfymodal-studio-filter-bar input,
  .comfymodal-studio-filter-bar select {
    min-height: 44px;
  }
  /* Experiment grid: reduce viewport padding to reclaim space */
  .comfymodal-studio-experiment-grid-viewport {
    padding: 8px 8px;
  }

  /* Running config panel is no longer absolutely positioned —
     it flows naturally in the control panel.  No narrow-screen
     override needed; the control panel handles its own scrolling. */
}

/* ── Card (generic) ──────────────────────────────────────── */

.comfymodal-studio-card {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 16px;
}

/* ── Snapshot / Backend Preset cards ─────────────────────── */

.comfymodal-studio-snapshot-card,
.comfymodal-studio-preset-card {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  padding: 10px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.comfymodal-studio-snapshot-card:hover,
.comfymodal-studio-preset-card:hover {
  border-color: #444;
}
.comfymodal-studio-snapshot-card.active,
.comfymodal-studio-preset-card.active {
  border-color: var(--color-accent, #5a7fdb);
}
.comfymodal-studio-snapshot-card h4,
.comfymodal-studio-preset-card h4 {
  margin: 0 0 2px;
  font-size: 12px;
  font-weight: 600;
  color: #d0d0d0;
}
.comfymodal-studio-snapshot-card p,
.comfymodal-studio-preset-card p {
  margin: 0;
  font-size: 11px;
  color: #555;
}

/* ── Status badges ───────────────────────────────────────── */

.comfymodal-studio-status-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.comfymodal-studio-status-badge.ok {
  background: #0a2a0a;
  color: #4ade80;
  border: 1px solid #1a4a1a;
}
.comfymodal-studio-status-badge.warn {
  background: #2a1a00;
  color: #fbbf24;
  border: 1px solid #4a3a00;
}
.comfymodal-studio-status-badge.error {
  background: #2a0a0a;
  color: #f87171;
  border: 1px solid #4a1a1a;
}
.comfymodal-studio-status-badge.neutral {
  background: #111;
  color: #888;
  border: 1px solid #2a2a2a;
}

/* ── Features chip grid ──────────────────────────────────── */

.comfymodal-studio-features-chip-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
button.comfymodal-studio-feature-chip {
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
}
.comfymodal-studio-feature-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: 3px;
  border: 1px solid #2a2a2a;
  background: #0a0a0a;
  color: #888;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
  user-select: none;
}
.comfymodal-studio-feature-chip:hover {
  border-color: #444;
  background: #1a1a1a;
}
.comfymodal-studio-feature-chip.checked,
.comfymodal-studio-feature-chip[aria-pressed="true"] {
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.18));
  border-color: var(--color-accent, #5a7fdb);
  color: var(--color-accent, #5a7fdb);
}
.comfymodal-studio-feature-chip .chip-check {
  display: none;
}
.comfymodal-studio-feature-chip.checked .chip-check,
.comfymodal-studio-feature-chip[aria-pressed="true"] .chip-check {
  display: inline;
}

/* ── Settings: compact rows ──────────────────────────────── */

.comfymodal-studio-settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #1a1a1a;
  font-size: 12px;
}
.comfymodal-studio-settings-row:last-child {
  border-bottom: none;
}
.comfymodal-studio-settings-row-label {
  color: #a0a0a0;
}
.comfymodal-studio-settings-row-value {
  color: #d0d0d0;
  text-align: right;
  font-size: 11px;
}

/* ── Settings: search, banner, resets, groups (v2 page) ─── */

.comfymodal-settings-search-wrap {
  margin-bottom: 4px;
}
.comfymodal-settings-search {
  width: 100%;
  box-sizing: border-box;
  font-size: 12px;
  padding: 6px 8px;
}
.comfymodal-settings-search::-webkit-search-cancel-button {
  cursor: pointer;
}
.comfymodal-settings-search-results {
  font-size: 11px;
  color: #888;
  margin-top: 4px;
}
.comfymodal-settings-row-hidden {
  display: none !important;
}

.comfymodal-settings-restart-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #2a1a00;
  color: #fbbf24;
  border: 1px solid #4a3a00;
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 12px;
}
.comfymodal-settings-restart-badge {
  display: inline-block;
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border-radius: 3px;
  background: #2a1a00;
  color: #fbbf24;
  border: 1px solid #4a3a00;
  margin-left: 6px;
  white-space: nowrap;
}
.comfymodal-settings-row-value-inline {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.comfymodal-studio-settings-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.comfymodal-studio-settings-section-head h3 {
  margin: 0;
}
.comfymodal-settings-section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.comfymodal-settings-reset-section-btn {
  background: transparent;
  color: #666;
  border: 1px solid #2a2a2a;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-family: inherit;
  transition: color 0.15s, border-color 0.15s;
}
.comfymodal-settings-reset-section-btn:hover {
  color: #aaa;
  border-color: #444;
}
.comfymodal-settings-reset-confirm {
  font-size: 11px;
  color: #4ade80;
}

.comfymodal-settings-control {
  padding: 6px 0;
  border-bottom: 1px solid #1a1a1a;
}
.comfymodal-settings-control .comfymodal-studio-settings-row {
  padding: 0;
  border-bottom: none;
}
.comfymodal-settings-control:last-child {
  border-bottom: none;
}
.comfymodal-studio-settings-hint {
  font-size: 10px;
  color: #666;
  margin-top: 2px;
}
.comfymodal-studio-settings-info {
  font-size: 11px;
  color: #777;
  margin: 4px 0;
}
.comfymodal-studio-settings-status {
  font-size: 10px;
  color: #888;
  margin-top: 3px;
}

.comfymodal-settings-segmented {
  display: inline-flex;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid #333;
  background: #0a0a0a;
}
.comfymodal-settings-segment {
  background: transparent;
  color: #888;
  border: none;
  padding: 4px 12px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
}
.comfymodal-settings-segment + .comfymodal-settings-segment {
  border-left: 1px solid #333;
}
.comfymodal-settings-segment:hover {
  color: #d0d0d0;
}
.comfymodal-settings-segment.active {
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.18));
  color: var(--color-accent, #5a7fdb);
}

.comfymodal-settings-range-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
  min-width: 200px;
}
.comfymodal-settings-range {
  flex: 1;
  accent-color: var(--color-accent, #5a7fdb);
}
.comfymodal-settings-range-value {
  font-size: 11px;
  color: #d0d0d0;
  min-width: 28px;
  text-align: right;
}
.comfymodal-settings-checkbox {
  width: 16px;
  height: 16px;
  accent-color: #3a6fcc;
}

.comfymodal-settings-group {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #2a2a2a;
}
.comfymodal-settings-group-title {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.comfymodal-settings-link {
  color: var(--color-accent, #5a7fdb);
  cursor: pointer;
  font-size: 12px;
  text-decoration: none;
}
.comfymodal-settings-link:hover {
  text-decoration: underline;
}

.comfymodal-settings-footer {
  margin-top: 4px;
}
.comfymodal-settings-footer-inner {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
}
.comfymodal-settings-footer-note {
  font-size: 11px;
  color: #666;
  margin: 0;
}
.comfymodal-settings-reset-all-btn {
  align-self: flex-start;
  width: auto;
}
.comfymodal-settings-open-folder {
  width: 100%;
}
.comfymodal-settings-legacy-open {
  width: 100%;
}

/* ── Backend count cards ─────────────────────────────────── */

.comfymodal-studio-stat-card {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  padding: 8px 12px;
  font-size: 12px;
}
.comfymodal-studio-stat-card .stat-value {
  font-weight: 600;
  color: #d0d0d0;
  min-width: 24px;
}

/* ── Axis popover ────────────────────────────────────────── */

.comfymodal-studio-axis-popover {
  background: #111;
  border: 1px solid #333;
  border-radius: 3px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}

/* ── Metadata Section ──────────────────────────────────────── */

.comfymodal-studio-metadata-section {
  background: #0f0f0f;
  border: 1px solid #222;
  border-radius: 3px;
  padding: 6px 10px;
  font-size: 11px;
  line-height: 1.5;
  flex-shrink: 0;
}

.comfymodal-studio-metadata-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.comfymodal-studio-metadata-status {
  font-weight: 600;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.comfymodal-studio-metadata-prompt,
.comfymodal-studio-metadata-neg-prompt {
  color: #aaa;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

.comfymodal-studio-metadata-source {
  color: #888;
  font-size: 10px;
}

.comfymodal-studio-metadata-duration,
.comfymodal-studio-metadata-time {
  color: #666;
  font-size: 10px;
}

.comfymodal-studio-metadata-settings {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px solid #1a1a1a;
}

.comfymodal-studio-metadata-setting {
  font-size: 10px;
  color: #777;
}

.comfymodal-studio-metadata-error {
  margin-top: 4px;
  padding: 4px 6px;
  background: #1a0a0a;
  border: 1px solid #3a0a0a;
  border-radius: 2px;
  color: #f87171;
  font-size: 10px;
}

.comfymodal-studio-metadata-advanced,
.comfymodal-studio-metadata-note-panel {
  margin-top: 4px;
  padding: 4px 6px;
  background: #0a0a0a;
  border: 1px solid #1a1a1a;
  border-radius: 2px;
}

.comfymodal-studio-metadata-advanced-toggle {
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
}

/* ── Progress Section ──────────────────────────────────── */

.comfymodal-studio-progress-section {
  background: #0f0f0f;
  border: 1px solid #222;
  border-radius: 3px;
  padding: 6px 10px;
  font-size: 11px;
  line-height: 1.5;
}

.comfymodal-studio-progress-bar-track {
  width: 100%;
  height: 8px;
  background: #1a1a1a;
  border-radius: 4px;
  overflow: hidden;
}

.comfymodal-studio-progress-bar-fill {
  height: 100%;
  background: var(--color-accent, #5a7fdb);
  border-radius: 4px;
  transition: width 0.3s ease;
}

/* ── Favorite Star (also <button> variant) ────────────── */

.comfymodal-studio-favorite-star {
  cursor: pointer;
  font-size: 16px;
  user-select: none;
  transition: transform 0.15s, color 0.15s;
  background: none;
  border: none;
  padding: 0;
  font-family: inherit;
  line-height: 1;
  color: inherit;
}

.comfymodal-studio-favorite-star:hover {
  transform: scale(1.2);
}

.comfymodal-studio-favorite-star:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

/* ── Note Editor ───────────────────────────────────────── */

.comfymodal-studio-note-editor {
  margin-top: 4px;
}

.comfymodal-studio-note-editor textarea {
  font-family: inherit;
}

/* ── Timing Card ─────────────────────────────────────────── */

.comfymodal-studio-timing-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin-top: 4px;
  padding: 4px 8px;
  background: #0a0a0a;
  border: 1px solid #1a1a1a;
  border-radius: 3px;
  font-size: 10px;
  line-height: 1.5;
}

.comfymodal-studio-timing-e2e {
  font-weight: 600;
  color: #d0d0d0;
  font-size: 11px;
}

.comfymodal-studio-timing-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px 6px;
  align-items: center;
}

.comfymodal-studio-timing-tag {
  color: #888;
  font-size: 9px;
  padding: 1px 4px;
  background: #1a1a1a;
  border-radius: 2px;
  white-space: nowrap;
}

.comfymodal-studio-timing-quality {
  font-size: 8px;
  color: #fbbf24;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-left: auto;
}

.comfymodal-studio-timing-quality:empty {
  display: none;
}

.comfymodal-studio-advanced-timing-toggle {
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  color: #666 !important;
}

.comfymodal-studio-advanced-timing-panel {
  width: 100%;
}

.comfymodal-studio-advanced-timing-panel div {
  font-size: 9px;
  line-height: 1.5;
  word-break: break-all;
}

/* ── Compat: old-style timing-summary fallback ─────────── */

.comfymodal-studio-timing-summary {
  font-size: 10px;
  color: #888;
  margin-top: 2px;
  padding: 2px 0;
}

/* ── Filter Bar ────────────────────────────────────────── */

.comfymodal-studio-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  padding: 6px 8px;
  background: #0f0f0f;
  border: 1px solid #222;
  border-radius: 3px;
}

.comfymodal-studio-filter-bar input,
.comfymodal-studio-filter-bar select {
  font-family: inherit;
}

/* ── Pagination controls ──────────────────────────────── */

.comfymodal-studio-history .comfymodal-secondary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Focus-visible styles for interactive Studio elements ──── */

.comfymodal-studio-topnav button:focus-visible,
.comfymodal-studio-feature-tab:focus-visible,
.comfymodal-studio-history-card:focus-visible,
.comfymodal-studio-backend-tab:focus-visible,
.comfymodal-studio-backend-card:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 1px;
}

.comfymodal-studio-preview-overlay-close:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

/* ── Safe-area support ──────────────────────────────── */

@supports (padding: env(safe-area-inset-top)) {
  .comfymodal-studio-modal {
    padding-top: env(safe-area-inset-top, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
    padding-left: env(safe-area-inset-left, 0px);
    padding-right: env(safe-area-inset-right, 0px);
  }
}

/* ── Card-level favorite star positioning ─────────────── */

.comfymodal-studio-history-card {
  position: relative;
}

.comfymodal-studio-history-card .comfymodal-studio-favorite-star {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 2;
}

/* ── Experiment Tile (ungrouped History) ─────────────── */

.comfymodal-studio-experiment-tile {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 0;
  padding: 0;
  aspect-ratio: 1;
  border-color: #2a2a2a;
  transition: border-color 0.15s, opacity 0.15s;
}

.comfymodal-studio-experiment-tile.completed {
  border-color: #1a4a1a;
}

.comfymodal-studio-experiment-tile.failed {
  border-color: #4a1a1a;
}

.comfymodal-studio-experiment-tile.running {
  border-color: #4a3a00;
}

.comfymodal-studio-experiment-tile:hover {
  border-color: var(--color-accent, #5a7fdb) !important;
}

.comfymodal-studio-exp-tile-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 8px;
  font-weight: 700;
  color: #fff;
  background: var(--color-accent, #5a7fdb);
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.06em;
  line-height: 1.4;
  flex-shrink: 0;
}

.comfymodal-studio-exp-tile-title {
  font-size: 10px;
  font-weight: 600;
  color: #d0d0d0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-exp-tile-images {
  position: relative;
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.comfymodal-studio-exp-tile-grid {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 1px;
  background: #0a0a0a;
}

.comfymodal-studio-exp-tile-grid-img,
.comfymodal-studio-exp-tile-single-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.comfymodal-studio-exp-tile-grid-empty {
  background: #111;
  width: 100%;
  height: 100%;
}

.comfymodal-studio-exp-tile-single-img {
  position: absolute;
  top: 0;
  left: 0;
}

.comfymodal-studio-exp-tile-time,
.comfymodal-studio-history-card-time-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0,0,0,0.72);
  color: rgba(255,255,255,0.9);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 600;
  line-height: 1.5;
  pointer-events: none;
  z-index: 5;
  border: 1px solid rgba(255,255,255,0.06);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.comfymodal-studio-exp-tile-error {
  font-size: 9px;
  color: #f87171;
  padding: 0 8px 4px;
  width: 100%;
  box-sizing: border-box;
}

/* ── Carousel Experiment Badge ─────────────────────── */

.comfymodal-studio-carousel-item-experiment {
  border-color: var(--color-accent, #5a7fdb) !important;
  border-style: dashed;
}

.comfymodal-studio-carousel-item-experiment:hover {
  border-color: #7a9ffb !important;
}

.comfymodal-studio-carousel-exp-badge {
  position: absolute;
  top: 2px;
  left: 2px;
  font-size: 7px;
  font-weight: 700;
  color: #fff;
  background: var(--color-accent, #5a7fdb);
  padding: 1px 4px;
  border-radius: 2px;
  letter-spacing: 0.05em;
  line-height: 1.3;
  z-index: 3;
  pointer-events: none;
}

/* ── Override testing-styles for Nexus look ──────────────── */

.comfymodal-input,
.comfymodal-studio-textarea,
.comfymodal-studio-number-input,
.comfymodal-studio-select {
  background: #111 !important;
  border: 1px solid #2a2a2a !important;
  color: #d0d0d0 !important;
  border-radius: 2px !important;
}

.comfymodal-input:focus,
.comfymodal-studio-textarea:focus,
.comfymodal-studio-number-input:focus,
.comfymodal-studio-select:focus {
  border-color: var(--color-border-focus, #5a7fdb) !important;
  outline: none !important;
}

/* ── Scrollbar styling ───────────────────────────────────── */

.comfymodal-studio-control-panel::-webkit-scrollbar,
.comfymodal-studio-workspace::-webkit-scrollbar {
  width: 6px;
}

.comfymodal-studio-control-panel::-webkit-scrollbar-track,
.comfymodal-studio-workspace::-webkit-scrollbar-track {
  background: transparent;
}

.comfymodal-studio-control-panel::-webkit-scrollbar-thumb,
.comfymodal-studio-workspace::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 3px;
}

.comfymodal-studio-control-panel::-webkit-scrollbar-thumb:hover,
.comfymodal-studio-workspace::-webkit-scrollbar-thumb:hover {
  background: #444;
}

/* ── Wizard Mode (side-panel layout) ─────────────────────── */

.comfymodal-testing-overlay.comfymodal-studio-wizard-mode {
  justify-content: flex-end;
  align-items: stretch;
  padding: 8px;
  background: transparent;
  pointer-events: none;
}

.comfymodal-studio-wizard-mode.comfymodal-studio-modal {
  width: min(460px, calc(100vw - 16px));
  height: min(96vh, 1040px);
  max-width: calc(100vw - 16px);
  margin-left: auto;
  pointer-events: auto;
}

.comfymodal-studio-wizard-mode .comfymodal-studio-topnav,
.comfymodal-studio-wizard-mode .comfymodal-studio-pagecontainer {
  display: none;
}

.comfymodal-studio-wizard-mode .comfymodal-studio-body {
  overflow: hidden;
}

/* ── Wizard Overlay and Panel ────────────────────────────── */

.comfymodal-studio-wizard-overlay {
  width: 100%;
  flex: 1;
  min-width: 0;
  border-left: none;
  background: #0d0d0d;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
}

.comfymodal-studio-wizard-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

/* ── Wizard Header ───────────────────────────────────────── */

.comfymodal-studio-wizard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.comfymodal-studio-wizard-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.comfymodal-studio-wizard-close {
  background: transparent;
  border: none;
  color: #666;
  font-size: 20px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.comfymodal-studio-wizard-close:hover {
  color: #f87171;
}

/* ── Step Indicator ──────────────────────────────────────── */

.comfymodal-studio-wizard-steps {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  background: #0a0a0a;
  border-bottom: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.comfymodal-studio-wizard-step-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #1a1a1a;
  color: #555;
  font-size: 10px;
  font-weight: 600;
  border: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.comfymodal-studio-wizard-step-dot.active {
  background: var(--color-accent, #5a7fdb);
  color: #fff;
  border-color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-wizard-step-dot.done {
  background: #0a2a0a;
  color: #4ade80;
  border-color: #1a4a1a;
}

.comfymodal-studio-wizard-step-label {
  font-size: 10px;
  color: #555;
  white-space: nowrap;
}

.comfymodal-studio-wizard-step-label.active {
  color: #d0d0d0;
  font-weight: 500;
}

.comfymodal-studio-wizard-step-line {
  display: inline-block;
  width: 16px;
  height: 1px;
  background: #2a2a2a;
}

.comfymodal-studio-wizard-step-line.done {
  background: #4ade80;
}

/* ── Wizard Body ─────────────────────────────────────────── */

.comfymodal-studio-wizard-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  min-height: 0;
}

.comfymodal-studio-wizard-body::-webkit-scrollbar {
  width: 4px;
}

.comfymodal-studio-wizard-body::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 2px;
}

.comfymodal-studio-wizard-section-title {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 600;
  color: #d0d0d0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.comfymodal-studio-wizard-description {
  font-size: 11px;
  color: #777;
  margin: 0 0 12px;
}

/* ── Wizard Footer ───────────────────────────────────────── */

.comfymodal-studio-wizard-footer {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #2a2a2a;
  flex-shrink: 0;
}

.comfymodal-studio-wizard-footer button {
  flex: 1;
}

/* ── Feature List ────────────────────────────────────────── */

.comfymodal-studio-wizard-feature-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comfymodal-studio-wizard-feature-card {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.comfymodal-studio-wizard-feature-card:hover {
  border-color: #444;
  background: #1a1a1a;
}

.comfymodal-studio-wizard-feature-card.selected {
  border-color: var(--color-accent, #5a7fdb);
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.18));
}

.comfymodal-studio-wizard-feature-check {
  flex-shrink: 0;
  padding-top: 1px;
}

.comfymodal-studio-wizard-checkbox {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: 1px solid #444;
  border-radius: 3px;
  font-size: 11px;
  color: transparent;
  background: transparent;
}

.comfymodal-studio-wizard-checkbox.checked {
  background: var(--color-accent, #5a7fdb);
  border-color: var(--color-accent, #5a7fdb);
  color: #fff;
}

.comfymodal-studio-wizard-feature-info {
  flex: 1;
  min-width: 0;
}

.comfymodal-studio-wizard-feature-info strong {
  font-size: 12px;
  color: #d0d0d0;
}

/* ── Binding List ────────────────────────────────────────── */

.comfymodal-studio-wizard-binding-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.comfymodal-studio-wizard-binding-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  transition: border-color 0.15s, background 0.15s;
}

.comfymodal-studio-wizard-binding-row:hover {
  border-color: #444;
}

.comfymodal-studio-wizard-binding-row.bound {
  border-color: #1a4a1a;
}

.comfymodal-studio-wizard-binding-row.capturing {
  border-color: #fbbf24;
  background: #1a1a00;
}

.comfymodal-studio-wizard-binding-row.capturing-active {
  border-color: var(--color-accent, #5a7fdb);
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.18));
}

.comfymodal-studio-wizard-binding-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.comfymodal-studio-wizard-binding-status {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ── Graph unavailable banner ────────────────────────────── */

.comfymodal-studio-wizard-graph-unavailable {
  background: #2a0a0a;
  border: 1px solid #4a1a1a;
  border-radius: 3px;
  padding: 8px 12px;
  margin-bottom: 12px;
}

/* ── Wizard Spinner ──────────────────────────────────────── */

.comfymodal-studio-wizard-spinner {
  display: inline-block;
  width: 24px;
  height: 24px;
  border: 2px solid #2a2a2a;
  border-top-color: var(--color-accent, #5a7fdb);
  border-radius: 50%;
  animation: comfymodal-spin 0.8s linear infinite;
  margin-top: 12px;
}

@keyframes comfymodal-spin {
  to { transform: rotate(360deg); }
}

/* ── Details form ────────────────────────────────────────── */

.comfymodal-studio-wizard-details-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── Backend Action Bar ──────────────────────────────────── */

.comfymodal-studio-backend-action-bar {
  padding: 8px 0 0;
}

/* ── Status Banner (preset detail) ─────────────────────── */

.comfymodal-studio-status-banner {
  padding: 6px 10px;
  border-radius: 3px;
  margin-bottom: 8px;
  font-size: 11px;
}
.comfymodal-studio-status-banner.runnable {
  background: var(--color-success-bg, rgba(74, 222, 128, 0.12));
  border: 1px solid var(--color-success, #4ade80);
  color: var(--color-success, #4ade80);
}
.comfymodal-studio-status-banner.archived {
  background: var(--color-danger-bg, rgba(239, 68, 68, 0.12));
  border: 1px solid var(--color-danger, #ef4444);
  color: var(--color-danger, #ef4444);
}
.comfymodal-studio-status-banner.not-runnable {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.12));
  border: 1px solid var(--color-warning, #f59e0b);
  color: var(--color-warning, #f59e0b);
}

/* ── Runnable Checklist ─────────────────────────────────── */

.comfymodal-studio-checklist {
  margin-bottom: 6px;
  padding: 6px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  list-style: none;
  margin: 4px 0;
}
.comfymodal-studio-checklist-item {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 2px 0;
  font-size: 10px;
}

/* ── Experiment Grid Viewport ────────────────────────────── */

.comfymodal-studio-experiment-grid-viewport {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: hidden;
  padding: 12px 16px;
  background-image: radial-gradient(#222 1px, transparent 1px);
  background-size: 30px 30px;
}

.comfymodal-studio-experiment-grid-building {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: #555;
  font-size: 12px;
  font-style: italic;
}

.comfymodal-studio-experiment-grid-outer {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.comfymodal-studio-experiment-grid-outer::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.comfymodal-studio-experiment-grid-outer::-webkit-scrollbar-track {
  background: transparent;
}
.comfymodal-studio-experiment-grid-outer::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 3px;
}

.comfymodal-studio-experiment-grid-group {
  margin: 0;
  padding-bottom: 14px;
}

.comfymodal-studio-experiment-grid-group + .comfymodal-studio-experiment-grid-group {
  border-top: 1px solid #2a2a2a;
  padding-top: 14px;
}

.comfymodal-studio-experiment-grid-group-label {
  font-size: 11px;
  font-weight: 600;
  color: #888;
  margin: 0 0 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.comfymodal-studio-experiment-grid-container {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}

.comfymodal-studio-experiment-grid-row {
  display: flex;
  flex-wrap: wrap;
  align-self: center;
  width: max-content;
  gap: 10px;
  align-items: stretch;
}

.comfymodal-studio-experiment-grid-row-cells {
  display: flex;
  gap: 10px;
  flex: 0 0 auto;
  min-width: 0;
}

.comfymodal-studio-experiment-grid-corner {
  width: 60px;
  flex-shrink: 0;
  font-size: 10px;
  color: #555;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 4px;
  overflow: hidden;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.comfymodal-studio-experiment-grid-row-label {
  width: 60px;
  flex-shrink: 0;
  font-size: 10px;
  color: #aaa;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 4px;
  font-weight: 500;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  max-width: 140px;
  line-height: 1.3;
}

.comfymodal-studio-experiment-grid-header {
  flex: 0 0 313px;
  width: 313px;
  min-width: 150px;
  max-width: 313px;
  font-size: 10px;
  color: #aaa;
  text-align: center;
  padding: 2px 4px;
  font-weight: 500;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Prompt-specific headers: no width cap — flex to match cell column.
   Text lives in an inner .*-prompt-text element that caps width &
   height for readability. */
.comfymodal-studio-experiment-grid-header.is-prompt {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-weight: 400;
  overflow: visible;
  text-overflow: clip;
  line-height: 1.4;
  padding: 4px 6px;
}

/* Inner element for prompt text in column headers: readable
   max inline width, capped height with scroll, no single-line
   ellipsis. Full text exposed via title/aria-label on the span. */
.comfymodal-studio-experiment-grid-header-prompt-text {
  display: block;
  max-width: 60ch;
  width: 100%;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  max-height: 7em;               /* ~5 lines at line-height 1.4 */
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #2a2a2a transparent;
  text-align: center;
  line-height: 1.4;
}

.comfymodal-studio-experiment-grid-header-prompt-text::-webkit-scrollbar {
  width: 4px;
}
.comfymodal-studio-experiment-grid-header-prompt-text::-webkit-scrollbar-track {
  background: transparent;
}
.comfymodal-studio-experiment-grid-header-prompt-text::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 2px;
}

/* Row label as prompt axis: grow width for readability without
   becoming hundreds of px wide. Inner element handles wrapping. */
.comfymodal-studio-experiment-grid-row-label.is-prompt {
  width: auto;
  min-width: 80px;
  max-width: 220px;
  padding: 4px 8px;
  align-items: flex-start;
  white-space: normal;
  overflow: visible;
}

.comfymodal-studio-experiment-grid-row-label-prompt-text {
  display: block;
  max-width: 60ch;
  width: 100%;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  max-height: 7em;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #2a2a2a transparent;
  text-align: right;
  line-height: 1.4;
}

.comfymodal-studio-experiment-grid-row-label-prompt-text::-webkit-scrollbar {
  width: 4px;
}
.comfymodal-studio-experiment-grid-row-label-prompt-text::-webkit-scrollbar-track {
  background: transparent;
}
.comfymodal-studio-experiment-grid-row-label-prompt-text::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 2px;
}

/* ── Experiment Grid Cell — Card Redesign ────────────── */

.comfymodal-studio-experiment-grid-cell {
  flex: 0 1 313px;
  width: 313px;
  min-width: 150px;
  max-width: 626px;
  min-height: var(--cell-min-height, 60px);
  max-height: none;
  border: 1px solid #222;
  border-radius: 8px;
  background: #141414;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  padding: 0;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
  position: relative;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  color: inherit;
  overflow: hidden;
  box-shadow: 0 2px 6px rgba(0,0,0,0.4);
  contain: layout style paint;
  will-change: transform;
  -webkit-tap-highlight-color: transparent;
}

.comfymodal-studio-experiment-grid-cell:hover {
  border-color: #00d1b2;
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0,209,178,0.20);
}

.comfymodal-studio-experiment-grid-cell:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

.cm-exp-cell-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.cm-exp-cell-imgwrap {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  background: #1a1a1a;
  overflow: hidden;
  flex-shrink: 0;
}

.cm-exp-cell-image {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
  border-radius: 0;
  opacity: 1;
  transition: opacity 0.3s;
}

.cm-exp-cell-loading,
.cm-exp-cell-icon,
.cm-exp-cell-placeholder {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.cm-exp-cell-loading {
  width: 24px;
  height: 24px;
  border: 2px solid #333;
  border-top-color: var(--color-accent, #5a7fdb);
  border-radius: 50%;
  animation: comfymodal-spin 0.8s linear infinite;
}

.cm-exp-cell-icon {
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
  pointer-events: none;
}

.cm-exp-cell-icon-done {
  color: #4ade80;
}

.cm-exp-cell-icon-fail {
  color: #f87171;
}

.cm-exp-cell-icon-skip {
  color: #fbbf24;
}

.cm-exp-cell-icon-interrupt {
  color: #fb923c;
}

.cm-exp-cell-placeholder {
  width: 60%;
  height: 60%;
  min-height: 30px;
  border: 1px dashed #333;
  border-radius: 4px;
}

/* ── Badges on image (order + timing) ────────────────── */

.cm-exp-cell-badge {
  position: absolute;
  background: rgba(0,0,0,0.78);
  color: rgba(255,255,255,0.92);
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 10px;
  pointer-events: none;
  z-index: 5;
  line-height: 1.5;
  border: 1px solid rgba(255,255,255,0.08);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.cm-exp-cell-index {
  bottom: 8px;
  left: 8px;
}

.cm-exp-cell-time {
  bottom: 8px;
  right: 8px;
}



/* ── Status border colours on the cell card ──────────── */

.comfymodal-studio-experiment-grid-cell.completed {
  border-color: #1a4a1a;
}

.comfymodal-studio-experiment-grid-cell.failed {
  border-color: #4a1a1a;
}

.comfymodal-studio-experiment-grid-cell.skipped {
  border-color: #3a3a00;
  opacity: 0.75;
}

.comfymodal-studio-experiment-grid-cell.interrupted {
  border-color: #4a2a00;
  opacity: 0.75;
}

.comfymodal-studio-experiment-grid-cell.running {
  border-color: #00d1b2;
  box-shadow: 0 0 8px rgba(0,209,178,0.25);
}

.comfymodal-studio-experiment-grid-cell.selected {
  border-color: #fbbf24;
  box-shadow: 0 0 12px rgba(251, 191, 36, 0.30);
}

.comfymodal-studio-experiment-grid-cell-empty {
  cursor: default;
  opacity: 0.35;
  font-size: 10px;
  color: #555;
  min-width: 60px;
  min-height: 60px;
  flex: 0 1 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
}

/* ── Stack layout for 3+ varying axes ────────────────── */

.comfymodal-studio-experiment-grid-cell-stack {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 150px;
}

.comfymodal-studio-experiment-grid-cell-stack > .comfymodal-studio-experiment-grid-cell {
  flex: none;
  min-width: 0;
  min-height: 120px;
}

.comfymodal-studio-experiment-grid-cell-stack > .comfymodal-studio-experiment-grid-cell + .comfymodal-studio-experiment-grid-cell::before {
  content: "";
  position: absolute;
  top: -8px;
  left: 0;
  right: 0;
  border-top: 1px solid #2a2a2a;
  pointer-events: none;
}

@media (max-width: 768px) {
  .comfymodal-studio-experiment-grid-header {
    flex-basis: 275px;
    width: 275px;
    max-width: 275px;
  }

  .comfymodal-studio-experiment-grid-row-cells {
    flex: 0 0 auto;
  }

  .comfymodal-studio-experiment-grid-cell {
    width: 275px;
    flex-basis: 275px;
  }
}

@media (max-width: 480px) {
  .comfymodal-studio-experiment-grid-row {
    align-self: flex-start;
  }

  .comfymodal-studio-experiment-grid-header {
    flex-basis: 213px;
    width: 213px;
    max-width: 213px;
  }

  .comfymodal-studio-experiment-grid-cell {
    width: 213px;
    flex-basis: 213px;
  }

  .comfymodal-studio-experiment-grid-row,
  .comfymodal-studio-experiment-grid-row-cells {
    gap: 8px;
  }

  .comfymodal-studio-experiment-grid-cell-stack {
    gap: 10px;
  }

  .comfymodal-studio-experiment-grid-cell-stack > .comfymodal-studio-experiment-grid-cell + .comfymodal-studio-experiment-grid-cell::before {
    top: -6px;
  }
}

.comfymodal-studio-experiment-grid-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #555;
  font-size: 12px;
  font-style: italic;
}

/* ── Experiment Progress Bars ─────────────────────────────── */

.comfymodal-studio-experiment-grid-progress {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: #0f0f0f;
  border: 1px solid #222;
  border-radius: 3px;
}

.comfymodal-studio-experiment-grid-progress-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.comfymodal-studio-experiment-grid-progress-label {
  font-size: 10px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  width: 80px;
  flex-shrink: 0;
}

.comfymodal-studio-experiment-grid-progress-track {
  flex: 1;
  height: 8px;
  background: #1a1a1a;
  border-radius: 4px;
  overflow: hidden;
}

.comfymodal-studio-experiment-grid-progress-fill {
  height: 100%;
  background: var(--color-accent, #5a7fdb);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.comfymodal-studio-experiment-grid-progress-pct {
  font-size: 10px;
  color: #aaa;
  width: 50px;
  text-align: right;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

/* ── Cell Detail Overlay ──────────────────────────────────── */

.comfymodal-studio-experiment-grid-detail-key {
  font-size: 11px;
  color: #888;
}

.comfymodal-studio-experiment-grid-detail-status {
  font-size: 11px;
  color: #888;
}

.comfymodal-studio-experiment-grid-detail-axes {
  border-top: 1px solid #2a2a2a;
  padding-top: 6px;
}

.comfymodal-studio-experiment-grid-detail-axes-title {
  font-size: 10px;
  font-weight: 600;
  color: #aaa;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}

.comfymodal-studio-experiment-grid-detail-axis-row {
  font-size: 11px;
  line-height: 1.6;
}

.comfymodal-studio-experiment-grid-detail-axis-key {
  color: #888;
}

.comfymodal-studio-experiment-grid-detail-axis-value {
  color: #f87171;
  font-weight: 600;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.comfymodal-studio-experiment-grid-detail-checkpoint {
  font-size: 10px;
  color: #666;
  border-top: 1px solid #2a2a2a;
  padding-top: 6px;
}

/* Non-varying values toggle in cell detail */
.comfymodal-studio-experiment-grid-detail-nonvarying-toggle {
  background: none;
  border: none;
  color: #666;
  cursor: pointer;
  font-family: inherit;
  font-size: 10px;
  padding: 6px 6px;
  text-align: left;
  width: 100%;
  border-radius: 2px;
  transition: background 0.15s, color 0.15s;
}
.comfymodal-studio-experiment-grid-detail-nonvarying-toggle:hover {
  background: #1a1a1a;
  color: #aaa;
}
.comfymodal-studio-experiment-grid-detail-nonvarying-content {
  display: none;
}
.comfymodal-studio-experiment-grid-detail-nonvarying-content.is-visible {
  display: block;
}
.comfymodal-studio-experiment-grid-detail-nonvarying-row {
  font-size: 10px;
  color: #777;
  line-height: 1.5;
  padding: 1px 0;
}
.comfymodal-studio-experiment-grid-detail-nonvarying-key {
  color: #888;
}
.comfymodal-studio-experiment-grid-detail-nonvarying-value {
  color: #aaa;
}

/* ── History V2 ─────────────────────────────────────────────── */

.comfymodal-studio-history-v2 {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

/* ── Toolbar ─────────────────────────────────────────────── */

.comfymodal-studio-history-v2-toolbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.comfymodal-studio-history-v2-toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
}

.comfymodal-studio-history-v2-toolbar-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.comfymodal-studio-history-v2-toolbar-label {
  font-size: 10px;
  font-weight: 600;
  color: #777;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.comfymodal-studio-history-v2-search {
  flex: 1 1 220px;
  min-width: 160px;
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 6px 10px;
  font-size: 12px;
  border-radius: 6px;
  font-family: inherit;
}

.comfymodal-studio-history-v2-search:focus {
  border-color: var(--color-accent, #5a7fdb);
  outline: none;
}

.comfymodal-studio-history-v2-select,
.comfymodal-studio-history-v2-date {
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 5px 8px;
  font-size: 12px;
  border-radius: 6px;
  font-family: inherit;
}

.comfymodal-studio-history-v2-select:focus,
.comfymodal-studio-history-v2-date:focus {
  border-color: var(--color-accent, #5a7fdb);
  outline: none;
}

.comfymodal-studio-history-v2-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #2a2a2a;
  background: #0d0d0d;
  color: #888;
  cursor: pointer;
  font-family: inherit;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
  user-select: none;
}

.comfymodal-studio-history-v2-toggle:hover {
  border-color: #444;
  color: #ccc;
}

.comfymodal-studio-history-v2-toggle[aria-pressed="true"] {
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.16));
  border-color: var(--color-accent, #5a7fdb);
  color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-history-v2-clear-all {
  background: none;
  border: none;
  color: #888;
  font-size: 11px;
  cursor: pointer;
  padding: 4px 6px;
  font-family: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.comfymodal-studio-history-v2-clear-all:hover {
  color: #f87171;
}

.comfymodal-studio-history-v2-result-count {
  font-size: 12px;
  color: #888;
  margin-left: auto;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.comfymodal-studio-history-v2-mode-banner {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #fbbf24;
  background: #2a1a00;
  border: 1px solid #4a3a00;
  border-radius: 999px;
  padding: 2px 10px;
  white-space: nowrap;
}

/* ── Results / grid ───────────────────────────────────────── */

.comfymodal-studio-history-v2-results {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.comfymodal-studio-history-v2-grid {
  display: grid;
  /* Column count comes from Settings → History → Grid columns via the
     --comfymodal-studio-history-columns custom property set inline on the
     page root (integer 2–8, default 6).  auto-fill + max() makes the user
     value the exact desktop track count — the calc term is one track's
     perfect share of the container including gap compensation (gap must
     stay 12px) minus a 0.5px rounding guard — while the 132px floor
     reflows to fewer equal columns on narrow containers instead of
     crushing cards. */
  grid-template-columns: repeat(
    auto-fill,
    minmax(
      max(
        132px,
        calc(
          (100% - (var(--comfymodal-studio-history-columns, 6) - 1) * 12px)
          / var(--comfymodal-studio-history-columns, 6)
          - 0.5px
        )
      ),
      1fr
    )
  );
  gap: 12px;
}

@media (max-width: 720px) {
  .comfymodal-studio-history-v2-grid {
    /* Narrow viewports keep the pre-setting legacy density (230px cards)
       regardless of the configured desktop column count. */
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  }
}

.comfymodal-studio-history-v2-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 48px 16px;
  color: #888;
  font-size: 13px;
  text-align: center;
}

.comfymodal-studio-history-v2-state p {
  margin: 0;
}

.comfymodal-studio-history-v2-state-error {
  color: #f87171;
}

/* ── Cards (sparse) ───────────────────────────────────────── */

.comfymodal-studio-history-v2-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
  min-width: 0;
  transition: border-color 0.15s, background 0.15s;
}

.comfymodal-studio-history-v2-card:hover {
  border-color: var(--color-accent, #5a7fdb);
  background: #141414;
}

.comfymodal-studio-history-v2-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.comfymodal-studio-history-v2-card-thumb {
  position: relative;
  aspect-ratio: 4 / 3;
  border-radius: 6px;
  overflow: hidden;
  background: #0a0a0a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.comfymodal-studio-history-v2-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.comfymodal-studio-history-v2-noimage {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #666;
  font-size: 11px;
  padding: 8px;
  background: #0a0a0a;
  border: 1px dashed #2a2a2a;
  border-radius: 6px;
  box-sizing: border-box;
}

.comfymodal-studio-history-v2-card-thumb .comfymodal-studio-history-v2-noimage {
  position: absolute;
  inset: 0;
  border: none;
  border-radius: 0;
}

.comfymodal-studio-history-v2-card-prompt {
  font-size: 12px;
  line-height: 1.4;
  color: #d0d0d0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.comfymodal-studio-history-v2-card-name {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-history-v2-card-counts {
  font-size: 12px;
  font-weight: 500;
  color: #aaa;
}

.comfymodal-studio-history-v2-card-meta {
  font-size: 11px;
  color: #888;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-history-v2-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.comfymodal-studio-history-v2-card-time {
  font-size: 10px;
  color: #666;
  font-variant-numeric: tabular-nums;
}

/* 2x2 cover for experiment cards */
.comfymodal-studio-history-v2-cover {
  display: grid;
  grid-template-columns: 1fr 1fr;
  aspect-ratio: 1 / 1;
  gap: 3px;
}

.comfymodal-studio-history-v2-cover-slot {
  position: relative;
  overflow: hidden;
  border-radius: 4px;
  background: #0a0a0a;
}

.comfymodal-studio-history-v2-cover-empty {
  border: 1px dashed #2a2a2a;
}

/* ── Status chips ─────────────────────────────────────────── */

.comfymodal-studio-history-v2-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid;
  white-space: nowrap;
}

.comfymodal-studio-history-v2-chip::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.comfymodal-studio-history-v2-chip.status-success {
  color: #4ade80;
  background: #0a2a0a;
  border-color: #1a4a1a;
}

.comfymodal-studio-history-v2-chip.status-completed {
  color: #4ade80;
  background: #0a2a0a;
  border-color: #1a4a1a;
}

.comfymodal-studio-history-v2-chip.status-failed {
  color: #f87171;
  background: #2a0a0a;
  border-color: #4a1a1a;
}

.comfymodal-studio-history-v2-chip.status-canceled {
  color: #9ca3af;
  background: #161616;
  border-color: #3a3a3a;
}

.comfymodal-studio-history-v2-chip.status-interrupted {
  color: #fbbf24;
  background: #2a1a00;
  border-color: #4a3a00;
}

.comfymodal-studio-history-v2-chip.status-partial {
  color: #fbbf24;
  background: #2a1a00;
  border-color: #4a3a00;
}

.comfymodal-studio-history-v2-chip.status-completed_with_failures {
  color: #fbbf24;
  background: #2a1a00;
  border-color: #4a3a00;
}

.comfymodal-studio-history-v2-chip.status-running {
  color: #60a5fa;
  background: #0a1a2a;
  border-color: #1a3a5a;
}

/* ── Favorite star ────────────────────────────────────────── */

.comfymodal-studio-history-v2-fav {
  background: none;
  border: none;
  color: #fbbf24;
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 4px;
}

.comfymodal-studio-history-v2-fav:hover {
  color: #fde68a;
}

/* ── Load more ────────────────────────────────────────────── */

.comfymodal-studio-history-v2-load-more {
  align-self: center;
  background: #1a1a1a;
  color: #aaa;
  border: 1px solid #333;
  padding: 6px 18px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.comfymodal-studio-history-v2-load-more:hover:not(:disabled) {
  background: #222;
  color: #d0d0d0;
  border-color: #444;
}

.comfymodal-studio-history-v2-load-more:disabled {
  opacity: 0.6;
  cursor: default;
}

/* ── Overflow menus ───────────────────────────────────────── */

.comfymodal-studio-history-v2-menu {
  z-index: 10060;
  background: #1a1a1a;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  padding: 4px;
  min-width: 150px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}

.comfymodal-studio-history-v2-menu-item {
  display: block;
  width: 100%;
  box-sizing: border-box;
  background: none;
  border: none;
  color: #ccc;
  font-size: 12px;
  text-align: left;
  padding: 6px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
}

.comfymodal-studio-history-v2-menu-item:hover:not(:disabled) {
  background: #2a2a2a;
  color: #fff;
}

.comfymodal-studio-history-v2-menu-item:disabled {
  color: #555;
  cursor: default;
}

.comfymodal-studio-history-v2-menu-btn {
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #1a1a1a;
  border: 1px solid #3a3a3a;
  color: #ccc;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.comfymodal-studio-history-v2-menu-btn:hover {
  color: #fff;
  border-color: var(--color-accent, #5a7fdb);
}

/* ── Generation detail overlay ────────────────────────────── */

.comfymodal-studio-history-v2-overlay {
  position: fixed;
  inset: 0;
  z-index: 10050;
  display: flex;
  align-items: center;
  justify-content: center;
}

.comfymodal-studio-history-v2-overlay-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.82);
}

.comfymodal-studio-history-v2-overlay-content {
  position: relative;
  width: min(1000px, 96vw);
  max-height: 90vh;
  overflow-y: auto;
  box-sizing: border-box;
  background: #0d0d0d;
  border: 1px solid #2a2a2a;
  border-radius: 10px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.comfymodal-studio-history-v2-overlay-close {
  position: sticky;
  top: 0;
  align-self: flex-end;
  background: transparent;
  border: none;
  color: #aaa;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 8px;
  z-index: 2;
}

.comfymodal-studio-history-v2-overlay-close:hover {
  color: #fff;
}

.comfymodal-studio-history-v2-overlay-body {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(280px, 1fr);
  gap: 18px;
  align-items: start;
}

.comfymodal-studio-history-v2-overlay-left,
.comfymodal-studio-history-v2-overlay-right {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.comfymodal-studio-history-v2-featured-img {
  max-width: 100%;
  border-radius: 8px;
  border: 1px solid #2a2a2a;
  display: block;
}

.comfymodal-studio-history-v2-featured-tile {
  aspect-ratio: 4 / 3;
  width: 100%;
  box-sizing: border-box;
}

.comfymodal-studio-history-v2-badge {
  font-size: 11px;
  color: #fbbf24;
  background: #2a1a00;
  border: 1px solid #4a3a00;
  border-radius: 6px;
  padding: 6px 10px;
}

/* Other outputs row */
.comfymodal-studio-history-v2-outputs-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.comfymodal-studio-history-v2-output-thumb-wrap {
  position: relative;
}

.comfymodal-studio-history-v2-output-thumb {
  width: 64px;
  height: 64px;
  border-radius: 6px;
  border: 2px solid #2a2a2a;
  overflow: hidden;
  background: #0a0a0a;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}

.comfymodal-studio-history-v2-output-thumb.featured {
  border-color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-history-v2-output-thumb-empty {
  color: #555;
  font-size: 18px;
}

/* Preview / Original slots */
.comfymodal-studio-history-v2-slots {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.comfymodal-studio-history-v2-slot {
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 8px;
  background: #0a0a0a;
}

.comfymodal-studio-history-v2-slot-title {
  font-size: 10px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}

.comfymodal-studio-history-v2-slot img {
  max-width: 100%;
  border-radius: 4px;
  display: block;
}

.comfymodal-studio-history-v2-slot-placeholder {
  font-size: 11px;
  color: #666;
  border: 1px dashed #2a2a2a;
  border-radius: 4px;
  padding: 14px;
  text-align: center;
}

.comfymodal-studio-history-v2-slot-error {
  font-size: 11px;
  color: #f87171;
  background: #2a0a0a;
  border: 1px solid #4a1a1a;
  border-radius: 4px;
  padding: 12px;
}

/* Right column sections */
.comfymodal-studio-history-v2-section {
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  background: #0f0f0f;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comfymodal-studio-history-v2-section-error {
  border-color: #4a1a1a;
}

.comfymodal-studio-history-v2-section-title {
  font-size: 10px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.comfymodal-studio-history-v2-row {
  display: flex;
  gap: 6px;
  font-size: 12px;
  line-height: 1.6;
  min-width: 0;
}

.comfymodal-studio-history-v2-row-key {
  color: #888;
  flex-shrink: 0;
}

.comfymodal-studio-history-v2-row-value {
  color: #d0d0d0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.comfymodal-studio-history-v2-run-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.comfymodal-studio-history-v2-error-line {
  color: #f87171;
}

.comfymodal-studio-history-v2-error-line .comfymodal-studio-history-v2-row-key {
  color: #f87171;
}

/* Parameters grid */
.comfymodal-studio-history-v2-params-table {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 6px;
}

.comfymodal-studio-history-v2-param {
  background: #0a0a0a;
  border: 1px solid #1a1a1a;
  border-radius: 6px;
  padding: 6px 8px;
}

.comfymodal-studio-history-v2-param-key {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #777;
}

.comfymodal-studio-history-v2-param-value {
  font-size: 12px;
  color: #d0d0d0;
  font-variant-numeric: tabular-nums;
}

/* Attempts */
.comfymodal-studio-history-v2-attempt {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.comfymodal-studio-history-v2-attempt-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.comfymodal-studio-history-v2-attempt-error {
  font-size: 11px;
  color: #f87171;
  line-height: 1.5;
}

/* Notes / actions */
.comfymodal-studio-history-v2-notes {
  width: 100%;
  box-sizing: border-box;
  min-height: 56px;
  resize: vertical;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 6px 8px;
  font-size: 12px;
  border-radius: 6px;
  font-family: inherit;
}

.comfymodal-studio-history-v2-notes:focus {
  border-color: var(--color-accent, #5a7fdb);
  outline: none;
}

.comfymodal-studio-history-v2-action-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.comfymodal-studio-history-v2-action-note {
  font-size: 11px;
  color: #fbbf24;
  min-width: 0;
  overflow-wrap: anywhere;
}

.comfymodal-studio-history-v2-generate {
  width: auto;
  padding: 6px 14px;
  font-size: 12px;
}

.comfymodal-studio-history-v2-timing-placeholder {
  font-size: 11px;
  color: #666;
  border: 1px dashed #2a2a2a;
  border-radius: 4px;
  padding: 10px;
  text-align: center;
}

/* ── Experiment detail page ───────────────────────────────── */

.comfymodal-studio-history-v2-experiment {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.comfymodal-studio-history-v2-experiment-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.comfymodal-studio-history-v2-back {
  align-self: flex-start;
}

.comfymodal-studio-history-v2-experiment-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.comfymodal-studio-history-v2-experiment-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #e0e0e0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.comfymodal-studio-history-v2-experiment-counts {
  font-size: 12px;
  color: #aaa;
}

.comfymodal-studio-history-v2-experiment-axis {
  font-size: 12px;
  color: #888;
}

.comfymodal-studio-history-v2-experiment-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.comfymodal-studio-history-v2-experiment-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
  align-content: start;
}

.comfymodal-studio-history-v2-experiment-grid.matrix {
  grid-template-columns: repeat(var(--matrix-cols, 4), minmax(0, 1fr));
}

.comfymodal-studio-history-v2-cell {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
  min-width: 0;
  transition: border-color 0.15s, background 0.15s;
}

.comfymodal-studio-history-v2-cell:hover {
  border-color: #444;
}

.comfymodal-studio-history-v2-cell.selected,
.comfymodal-studio-history-v2-cell[aria-pressed="true"] {
  border-color: var(--color-accent, #5a7fdb);
  background: #15181f;
}

.comfymodal-studio-history-v2-cell-thumb {
  aspect-ratio: 1 / 1;
  border-radius: 6px;
  overflow: hidden;
  background: #0a0a0a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.comfymodal-studio-history-v2-cell-empty {
  border: 1px dashed #2a2a2a;
  color: #666;
  font-size: 11px;
  text-align: center;
  padding: 4px;
  box-sizing: border-box;
}

.comfymodal-studio-history-v2-cell-axis {
  font-size: 10px;
  color: #888;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-history-v2-cell-detail-wrap {
  display: flex;
  flex-direction: column;
}

.comfymodal-studio-history-v2-cell-detail-hint {
  font-size: 12px;
  color: #666;
  border: 1px dashed #2a2a2a;
  border-radius: 8px;
  padding: 14px;
  text-align: center;
}

.comfymodal-studio-history-v2-cell-detail {
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  background: #0f0f0f;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── Focus visibility for all interactive elements ────────── */

.comfymodal-studio-history-v2 button:focus-visible,
.comfymodal-studio-history-v2 [role="button"]:focus-visible,
.comfymodal-studio-history-v2 input:focus-visible,
.comfymodal-studio-history-v2 select:focus-visible,
.comfymodal-studio-history-v2 textarea:focus-visible,
.comfymodal-studio-history-v2-overlay button:focus-visible,
.comfymodal-studio-history-v2-overlay [role="button"]:focus-visible,
.comfymodal-studio-history-v2-overlay input:focus-visible,
.comfymodal-studio-history-v2-overlay select:focus-visible,
.comfymodal-studio-history-v2-overlay textarea:focus-visible,
.comfymodal-studio-history-v2-experiment button:focus-visible,
.comfymodal-studio-history-v2-experiment [role="button"]:focus-visible,
.comfymodal-studio-history-v2-experiment input:focus-visible,
.comfymodal-studio-history-v2-experiment select:focus-visible,
.comfymodal-studio-history-v2-experiment textarea:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 1px;
}

/* ── Responsive: below 720px ──────────────────────────────── */

@media (max-width: 720px) {
  .comfymodal-studio-history-v2-grid {
    grid-template-columns: 1fr;
  }
  .comfymodal-studio-history-v2-overlay-body {
    grid-template-columns: 1fr;
  }
  .comfymodal-studio-history-v2-slots {
    grid-template-columns: 1fr;
  }
  .comfymodal-studio-history-v2-experiment-grid.matrix {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* ── Workflows page ─────────────────────────────────────── */

.comfymodal-studio-workflows {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.comfymodal-studio-workflows-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.comfymodal-studio-workflows-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.comfymodal-studio-workflows-header-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.comfymodal-studio-workflows-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.comfymodal-studio-workflows-count {
  font-size: 11px;
  color: #777;
  font-variant-numeric: tabular-nums;
}

.comfymodal-studio-workflows-header-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.comfymodal-studio-workflows-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  padding: 8px 10px;
  background: #0f0f0f;
  border: 1px solid #222;
  border-radius: 6px;
  flex-shrink: 0;
}

.comfymodal-studio-workflows-search {
  flex: 1 1 220px;
  min-width: 160px;
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 6px 10px;
  font-size: 12px;
  border-radius: 6px;
  font-family: inherit;
}
.comfymodal-studio-workflows-search:focus {
  border-color: var(--color-accent, #5a7fdb);
  outline: none;
}

.comfymodal-studio-workflows-select {
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 5px 8px;
  font-size: 12px;
  border-radius: 6px;
  font-family: inherit;
}
.comfymodal-studio-workflows-select:focus {
  border-color: var(--color-accent, #5a7fdb);
  outline: none;
}

.comfymodal-studio-workflows-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #2a2a2a;
  background: #0d0d0d;
  color: #888;
  cursor: pointer;
  font-family: inherit;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
  user-select: none;
}
.comfymodal-studio-workflows-toggle:hover {
  border-color: #444;
  color: #ccc;
}
.comfymodal-studio-workflows-toggle[aria-pressed="true"] {
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.16));
  border-color: var(--color-accent, #5a7fdb);
  color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-workflows-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 12px;
  overflow: hidden;
}

.comfymodal-studio-workflows-sidebar {
  width: 200px;
  min-width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  padding-right: 4px;
}

.comfymodal-studio-workflows-sidebar-label {
  font-size: 10px;
  font-weight: 600;
  color: #777;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.comfymodal-studio-workflows-folder-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.comfymodal-studio-workflows-folder-item {
  background: none;
  border: none;
  color: #888;
  font-size: 11px;
  text-align: left;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: background 0.15s, color 0.15s;
}
.comfymodal-studio-workflows-folder-item:hover {
  background: #1a1a1a;
  color: #ccc;
}
.comfymodal-studio-workflows-folder-item.active {
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.16));
  color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-workflows-grid {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  align-content: start;
  padding-right: 4px;
}

.comfymodal-studio-workflow-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  min-width: 0;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}
.comfymodal-studio-workflow-card:hover {
  border-color: var(--color-accent, #5a7fdb);
  background: #15181f;
  transform: translateY(-1px);
}

.comfymodal-studio-workflow-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 6px;
}

.comfymodal-studio-workflow-card-name {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.comfymodal-studio-workflow-card-folder {
  font-size: 10px;
  color: #777;
}

.comfymodal-studio-workflow-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  align-items: center;
  font-size: 10px;
  color: #777;
  margin-top: auto;
  padding-top: 2px;
}

.comfymodal-studio-workflow-card-source {
  font-size: 10px;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-workflows-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.comfymodal-studio-wf-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid #2a2a2a;
  background: #0a0a0a;
  color: #999;
  white-space: nowrap;
}
.comfymodal-studio-wf-chip.default {
  color: var(--color-accent, #5a7fdb);
  border-color: var(--color-accent, #5a7fdb);
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.12));
}
.comfymodal-studio-wf-chip .chip-x {
  cursor: pointer;
  color: #666;
  background: none;
  border: none;
  padding: 0 2px;
  font-size: 11px;
  line-height: 1;
}
.comfymodal-studio-wf-chip .chip-x:hover {
  color: #f87171;
}

.comfymodal-studio-workflows-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 48px 16px;
  color: #888;
  font-size: 13px;
  text-align: center;
}

.comfymodal-studio-workflows-link {
  color: var(--color-accent, #5a7fdb);
  text-decoration: none;
}
.comfymodal-studio-workflows-link:hover {
  text-decoration: underline;
}

/* ── Workflow detail ─────────────────────────────────────── */

.comfymodal-studio-workflow-detail {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding-right: 4px;
}

.comfymodal-studio-detail-top {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.comfymodal-studio-workflow-detail-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 14px 16px;
}

.comfymodal-studio-workflow-detail-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.comfymodal-studio-workflow-detail-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #e8e8e8;
  min-width: 0;
  overflow-wrap: anywhere;
  flex: 1;
}

.comfymodal-studio-workflow-detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 11px;
  color: #888;
}

.comfymodal-studio-workflow-detail-desc {
  margin: 0;
  font-size: 12px;
  color: #aaa;
  line-height: 1.5;
}

.comfymodal-studio-workflow-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.comfymodal-studio-tag-add {
  width: 120px !important;
  display: inline-block;
}
.comfymodal-studio-tag-add-wrap {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.comfymodal-studio-workflow-detail-source {
  font-size: 11px;
  color: #777;
  overflow-wrap: anywhere;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}

.comfymodal-studio-detail-edit-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── Run bar ─────────────────────────────────────────────── */

.comfymodal-studio-run-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #0f0f0f;
  border: 1px solid #222;
  border-radius: 8px;
  padding: 10px 14px;
  flex-shrink: 0;
}
.comfymodal-studio-run-bar .comfymodal-primary-btn {
  width: auto;
  min-width: 120px;
  padding: 8px 20px;
}
.comfymodal-studio-run-bar-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.comfymodal-studio-run-bar-version {
  font-size: 11px;
  font-weight: 600;
  color: #d0d0d0;
}
.comfymodal-studio-run-bar-hint {
  font-size: 11px;
  color: #777;
}

/* ── Generic detail sections ─────────────────────────────── */

.comfymodal-studio-section {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.comfymodal-studio-section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}

.comfymodal-studio-section-title {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  color: #a0a0a0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Versions list ───────────────────────────────────────── */

.comfymodal-studio-version-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.comfymodal-studio-version-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.comfymodal-studio-version-item:hover {
  border-color: #444;
  background: #121212;
}
.comfymodal-studio-version-item.active {
  border-color: var(--color-accent, #5a7fdb);
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.10));
}

.comfymodal-studio-version-item-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  flex: 1;
  min-width: 0;
}

.comfymodal-studio-version-number {
  font-weight: 600;
  color: #e0e0e0;
  font-size: 12px;
}

.comfymodal-studio-version-sub {
  color: #666;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.comfymodal-studio-version-reasons-toggle {
  background: none;
  border: none;
  color: var(--color-accent, #5a7fdb);
  font-size: 10px;
  cursor: pointer;
  font-family: inherit;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.comfymodal-studio-version-reasons-toggle:hover {
  color: #a5bff9;
}

.comfymodal-studio-version-reasons {
  padding-left: 2px;
}

/* ── Reasons ─────────────────────────────────────────────── */

.comfymodal-studio-reason-list {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.comfymodal-studio-reason-list li {
  font-size: 10px;
  color: #fbbf24;
  line-height: 1.4;
}
.comfymodal-studio-reason-list.dropped li {
  color: #fbbf24;
}

/* ── Dependencies placeholder ────────────────────────────── */

.comfymodal-studio-dependencies-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.comfymodal-studio-dependencies-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.comfymodal-studio-dependencies-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.comfymodal-studio-dependencies-note {
  font-size: 10px;
  color: #666;
  font-style: italic;
  margin: 0;
}

/* ── Mapping ─────────────────────────────────────────────── */

.comfymodal-studio-mapping-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.comfymodal-studio-mapping-summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  align-items: center;
}

.comfymodal-studio-mapping-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.comfymodal-studio-mapping-state {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  align-items: flex-start;
}

.comfymodal-studio-mapping-candidates {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comfymodal-studio-mapping-role-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
}

.comfymodal-studio-mapping-role-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.comfymodal-studio-role-label {
  font-size: 12px;
  font-weight: 600;
  color: #d0d0d0;
}
.comfymodal-studio-role-info {
  font-size: 10px;
  color: #666;
  font-variant-numeric: tabular-nums;
}
.comfymodal-studio-role-required {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #f87171;
}
.comfymodal-studio-role-hint {
  font-size: 9px;
  color: #777;
}

.comfymodal-studio-confirm-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: #2a1a00;
  border: 1px solid #4a3a00;
  border-radius: 6px;
  font-size: 11px;
  color: #fbbf24;
}
.comfymodal-studio-confirm-panel.incomplete {
  background: #2a0a0a;
  border-color: #4a1a1a;
  color: #f87171;
}

/* ── Presets ─────────────────────────────────────────────── */

.comfymodal-studio-preset-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comfymodal-studio-wf-preset-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
}
.comfymodal-studio-wf-preset-card.is-default {
  border-color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-wf-preset-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.comfymodal-studio-wf-preset-card-name {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: #e0e0e0;
}

.comfymodal-studio-wf-preset-card-desc {
  margin: 0;
  font-size: 11px;
  color: #777;
}

.comfymodal-studio-wf-preset-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* ── Preset editor ───────────────────────────────────────── */

.comfymodal-studio-preset-editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.comfymodal-studio-preset-editor .comfymodal-studio-backend-field {
  margin-bottom: 0;
}

.comfymodal-studio-editor-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comfymodal-studio-editor-block-title {
  font-size: 10px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0;
}

.comfymodal-studio-editor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
}

.comfymodal-studio-lora-rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.comfymodal-studio-lora-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.comfymodal-studio-lora-row .comfymodal-studio-wf-input {
  flex: 1;
}

/* ── Copy results ────────────────────────────────────────── */

.comfymodal-studio-copy-results {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.comfymodal-studio-copy-result-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  font-size: 11px;
}
.comfymodal-studio-copy-result-item.ok {
  border-color: #1a4a1a;
}
.comfymodal-studio-copy-result-item.warn {
  border-color: #4a3a00;
}

.comfymodal-studio-copy-result-name {
  font-weight: 600;
  color: #d0d0d0;
}

/* ── Notices ─────────────────────────────────────────────── */

.comfymodal-studio-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  background: #0a2a0a;
  border: 1px solid #1a4a1a;
  color: #4ade80;
  flex-shrink: 0;
}
.comfymodal-studio-notice.error {
  background: #2a0a0a;
  border-color: #4a1a1a;
  color: #f87171;
}
.comfymodal-studio-notice-dismiss {
  background: none;
  border: none;
  color: inherit;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  margin-left: auto;
  padding: 0 4px;
}

/* ── Workflows inputs / controls ─────────────────────────── */

.comfymodal-studio-wf-input {
  width: 100%;
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 5px 8px;
  font-size: 12px;
  border-radius: 4px;
  font-family: inherit;
}
.comfymodal-studio-wf-input:focus {
  border-color: var(--color-accent, #5a7fdb);
  outline: none;
}

.comfymodal-studio-wf-checkbox {
  accent-color: var(--color-accent, #5a7fdb);
  cursor: pointer;
}

/* ── Import dialog ───────────────────────────────────────── */

.comfymodal-studio-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 10040;
  display: flex;
  align-items: center;
  justify-content: center;
}
.comfymodal-studio-dialog-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
}
.comfymodal-studio-dialog {
  position: relative;
  width: min(560px, 94vw);
  max-height: 86vh;
  overflow-y: auto;
  box-sizing: border-box;
  background: #0d0d0d;
  border: 1px solid #2a2a2a;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.6);
}
.comfymodal-studio-dialog-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.comfymodal-studio-dialog-note {
  margin: 0;
  font-size: 11px;
  color: #888;
}
.comfymodal-studio-dialog-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
}
.comfymodal-studio-dialog-section-title {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  color: #a0a0a0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.comfymodal-studio-dialog-status {
  font-size: 11px;
  color: #aaa;
}
.comfymodal-studio-dialog-status.error {
  color: #f87171;
}
.comfymodal-studio-dialog-warning {
  font-size: 10px;
  color: #fbbf24;
}
.comfymodal-studio-dialog-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

/* ── Workflows focus visibility ──────────────────────────── */

.comfymodal-studio-workflows button:focus-visible,
.comfymodal-studio-workflows input:focus-visible,
.comfymodal-studio-workflows select:focus-visible,
.comfymodal-studio-workflows textarea:focus-visible,
.comfymodal-studio-dialog button:focus-visible,
.comfymodal-studio-dialog input:focus-visible,
.comfymodal-studio-dialog select:focus-visible,
.comfymodal-studio-dialog textarea:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 1px;
}

/* ── Workflows responsive ────────────────────────────────── */

@media (max-width: 768px) {
  .comfymodal-studio-workflows-body {
    flex-direction: column;
    overflow-y: auto;
  }
  .comfymodal-studio-workflows-sidebar {
    width: 100%;
    min-width: 0;
    max-height: 180px;
  }
  .comfymodal-studio-workflows-grid {
    overflow-y: visible;
  }
}

/* ── Workflows sub-nav (Workflows / Model Library) ───────── */

.comfymodal-studio-subnav {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #2a2a2a;
  margin-bottom: 12px;
  flex-shrink: 0;
  background: #0d0d0d;
}

.comfymodal-studio-subnav-btn {
  background: transparent;
  border: none;
  color: #666;
  padding: 7px 14px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}

.comfymodal-studio-subnav-btn:hover {
  color: #d0d0d0;
  background: #1a1a1a;
}

.comfymodal-studio-subnav-btn.active {
  color: var(--color-accent, #5a7fdb);
  border-bottom-color: var(--color-accent, #5a7fdb);
}

/* ── Model Library ───────────────────────────────────────── */

.comfymodal-studio-model-library {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.comfymodal-studio-model-library-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.comfymodal-studio-model-library-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #d0d0d0;
}

.comfymodal-studio-models-count {
  font-size: 11px;
  color: #888;
}

.comfymodal-studio-models-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.comfymodal-studio-rehash-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #888;
  cursor: pointer;
}

.comfymodal-studio-model-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.comfymodal-studio-model-row {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) auto auto 80px minmax(140px, 1.4fr) 90px 56px auto;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  font-size: 12px;
}

.comfymodal-studio-model-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.comfymodal-studio-model-name {
  font-weight: 600;
  color: #d0d0d0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-model-file {
  font-size: 11px;
  color: #777;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-model-size,
.comfymodal-studio-model-hash {
  color: #888;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.comfymodal-studio-model-path {
  color: #666;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-models-link {
  color: var(--color-accent, #5a7fdb);
  font-size: 11px;
  text-decoration: none;
}

.comfymodal-studio-models-link:hover {
  text-decoration: underline;
}

.comfymodal-studio-model-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  white-space: nowrap;
}

.comfymodal-studio-model-badge.installed {
  background: #0a2a0a;
  color: #4ade80;
  border: 1px solid #1a4a1a;
}

.comfymodal-studio-model-badge.missing {
  background: #2a0a0a;
  color: #f87171;
  border: 1px solid #4a1a1a;
}

.comfymodal-studio-model-badge.warning {
  background: #2a1a00;
  color: #fbbf24;
  border: 1px solid #4a3a00;
}

.comfymodal-studio-model-badge.unknown {
  background: #111;
  color: #888;
  border: 1px solid #2a2a2a;
}

/* In-progress states share the existing accent (running) family — no new
   palette. Hooks for dependency rows reporting downloading/queued truth. */
.comfymodal-studio-model-badge.downloading,
.comfymodal-studio-model-badge.queued {
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.18));
  color: var(--color-accent, #5a7fdb);
  border: 1px solid rgba(90, 127, 219, 0.45);
}

.comfymodal-studio-model-badge.type,
.comfymodal-studio-model-badge.role {
  background: #0d1526;
  color: #8ab0ff;
  border: 1px solid #1a2a4a;
}

.comfymodal-studio-models-empty {
  padding: 16px;
  color: #777;
  font-size: 12px;
  text-align: center;
  background: #111;
  border: 1px dashed #2a2a2a;
  border-radius: 4px;
}

.comfymodal-studio-model-detail-meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 12px;
  font-size: 11px;
}

.comfymodal-studio-model-detail-meta-row {
  display: contents;
}

.comfymodal-studio-model-detail-meta-key {
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  font-size: 10px;
  padding-top: 2px;
}

.comfymodal-studio-model-detail-meta-val {
  color: #d0d0d0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-download-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── Dependency section ─────────────────────────────────── */

.comfymodal-studio-dependency-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 10px;
}

.comfymodal-studio-dependency-banner.ready {
  background: #0a2a0a;
  color: #4ade80;
  border: 1px solid #1a4a1a;
}

.comfymodal-studio-dependency-banner.attention {
  background: #2a1a00;
  color: #fbbf24;
  border: 1px solid #4a3a00;
}

.comfymodal-studio-dependency-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.comfymodal-studio-dependency-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comfymodal-studio-dependency-row {
  display: flex;
  align-items: center;
  gap: 8px 12px;
  padding: 10px 12px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  font-size: 12px;
  flex-wrap: wrap;
}

.comfymodal-studio-dependency-name {
  color: #d0d0d0;
  font-weight: 500;
  flex: 1 1 200px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Status badges (installed/missing/warning/unknown/downloading/queued) sit
   at the card's trailing edge; role/type identity badges stay inline. */
.comfymodal-studio-dependency-row > .comfymodal-studio-model-badge:not(.role):not(.type) {
  margin-left: auto;
  flex-shrink: 0;
}

.comfymodal-studio-dependency-detail,
.comfymodal-studio-dependency-path {
  min-width: 0;
  max-width: 100%;
  flex: 0 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-dependency-detail {
  color: #888;
  font-size: 11px;
}

.comfymodal-studio-dependency-path {
  color: #666;
  font-size: 11px;
}

/* Row actions share one wrapping line; the status note always takes its
   own line so buttons never collide with feedback text. */
.comfymodal-studio-dependency-request {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}

.comfymodal-studio-dependency-request-note {
  flex-basis: 100%;
  min-width: 0;
}

/* ── Model picker (preset editor) ───────────────────────── */

.comfymodal-studio-model-picker {
  width: 100%;
  box-sizing: border-box;
  background: #111;
  border: 1px solid #2a2a2a;
  color: #d0d0d0;
  padding: 5px 8px;
  font-size: 12px;
  border-radius: 3px;
}

.comfymodal-studio-model-picker:focus {
  border-color: var(--color-border-focus, #5a7fdb);
  outline: none;
}

/* ── Workflow Portability (Phase G12) ────────────────────── */

.comfymodal-studio-portability-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  border: 1px solid var(--color-border, #333);
  background: transparent;
  color: inherit;
  font-family: inherit;
  font-size: 10px;
  padding: 2px 9px;
  cursor: pointer;
}
.comfymodal-studio-portability-chip.ok {
  border-color: var(--color-success, #4ade80);
  color: var(--color-success, #4ade80);
}
.comfymodal-studio-portability-chip.warn {
  border-color: var(--color-warning, #fbbf24);
  color: var(--color-warning, #fbbf24);
}
.comfymodal-studio-portability-chip.error {
  border-color: var(--color-danger, #f87171);
  color: var(--color-danger, #f87171);
}
.comfymodal-studio-portability-chip.neutral {
  color: var(--color-text-muted, #9ca3af);
}
.comfymodal-studio-portability-chip:hover {
  filter: brightness(1.15);
}
.comfymodal-studio-portability-chip:focus-visible {
  outline: 2px solid var(--color-border-focus, #5a7fdb);
  outline-offset: 1px;
}

.comfymodal-studio-portability-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}
.comfymodal-studio-portability-summary-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.comfymodal-studio-portability-meta {
  font-size: 11px;
  color: var(--color-text-muted, #9ca3af);
}
.comfymodal-studio-portability-version-context {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.comfymodal-studio-portability-counts {
  font-size: 11px;
  color: var(--color-text-muted, #9ca3af);
}

.comfymodal-studio-portability-issues {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 4px 0 8px;
}
.comfymodal-studio-portability-issue {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 6px 8px;
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 6px;
}
.comfymodal-studio-portability-issue-severity {
  flex: none;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid currentColor;
}
.comfymodal-studio-portability-issue.severity-high .comfymodal-studio-portability-issue-severity { color: var(--color-danger, #f87171); }
.comfymodal-studio-portability-issue.severity-medium .comfymodal-studio-portability-issue-severity { color: var(--color-warning, #fbbf24); }
.comfymodal-studio-portability-issue.severity-low .comfymodal-studio-portability-issue-severity,
.comfymodal-studio-portability-issue.severity-unknown .comfymodal-studio-portability-issue-severity { color: var(--color-text-muted, #9ca3af); }
.comfymodal-studio-portability-issue-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.comfymodal-studio-portability-issue-message {
  font-size: 11px;
}
.comfymodal-studio-portability-issue-hint {
  font-size: 10px;
  color: var(--color-text-muted, #9ca3af);
}

.comfymodal-studio-portability-targets {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 4px 0 10px;
}
.comfymodal-studio-portability-target-head,
.comfymodal-studio-portability-target-row {
  display: grid;
  grid-template-columns: 110px 90px 1fr;
  gap: 10px;
  align-items: start;
  padding: 4px 0;
}
.comfymodal-studio-portability-target-head {
  border-bottom: 1px solid var(--color-border, #2a2a2a);
}
.comfymodal-studio-portability-target-name {
  font-size: 11px;
  font-weight: 600;
}
.comfymodal-studio-portability-target-notes {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.comfymodal-studio-portability-target-reason {
  font-size: 10px;
  color: var(--color-text-muted, #9ca3af);
}
.comfymodal-studio-portability-target-advice {
  font-size: 10px;
  color: var(--color-text-muted, #9ca3af);
  font-style: italic;
}

.comfymodal-studio-portability-environment {
  border-top: 1px dashed var(--color-border, #2a2a2a);
  margin-top: 8px;
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.comfymodal-studio-portability-env-risk {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ══════════════════════════════════════════════════════════
   Phase I3 — Shared UI primitives foundation.
   Appended by the I3 primitives lane ONLY.  Page lanes
   (I4 History / I6 Workflows+Models / I7 Backend+Settings /
   I8 Playground) consume these classes; they do not redefine them.
   ══════════════════════════════════════════════════════════ */

/* ── I3: Shared loading state ────────────────────────────── */

.cm-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-secondary, #9aa3b2);
  font-size: 12px;
}
.cm-loading[data-size="page"] {
  justify-content: center;
  padding: 24px 0;
}
.cm-loading[data-size="inline"] {
  justify-content: flex-start;
  padding: 2px 0;
}
.cm-loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid #2a2a2a;
  border-top-color: var(--color-accent, #5a7fdb);
  border-radius: 50%;
  flex-shrink: 0;
  /* ONE shared spinner animation source (the wizard keyframe). */
  animation: comfymodal-spin 0.8s linear infinite;
}
.cm-loading-label {
  white-space: nowrap;
}

/* ── I3: Shared chip base + tone system ──────────────────── */
/* Geometry/typography only — semantics live in [data-tone]. */

.cm-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid #2a2a2a;
  border-radius: 999px;
  font-family: inherit;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0.02em;
  white-space: nowrap;
  vertical-align: middle;
}

/* Shared tones. Existing Studio token palette only — no second color system. */
.cm-chip[data-tone="neutral"] {
  background: #111;
  color: var(--color-text-muted, #888);
  border-color: #2a2a2a;
}
.cm-chip[data-tone="ok"] {
  background: var(--color-success-bg, rgba(74, 222, 128, 0.12));
  color: var(--color-success, #4ade80);
  border-color: rgba(74, 222, 128, 0.35);
}
.cm-chip[data-tone="warn"] {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.12));
  color: var(--color-warning, #fbbf24);
  border-color: rgba(245, 158, 11, 0.35);
}
.cm-chip[data-tone="error"] {
  background: var(--color-danger-bg, rgba(239, 68, 68, 0.12));
  color: var(--color-danger, #ef4444);
  border-color: rgba(239, 68, 68, 0.35);
}
.cm-chip[data-tone="running"] {
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.18));
  color: var(--color-accent, #5a7fdb);
  border-color: rgba(90, 127, 219, 0.45);
}
.cm-chip[data-tone="meta"] {
  background: transparent;
  color: var(--color-text-secondary, #9aa3b2);
  border-color: var(--color-border-default, #2d2d3a);
}

/* Semantic family guards. Portability and Compatibility share geometry but
   MUST stay visually and semantically distinct families. */

/* Portability targets keep their Phase-G12 outline-pill presentation:
   transparent fill, tone-colored text/border only. */
.cm-chip.cm-chip--portability {
  background: transparent;
  box-shadow: none;
}

/* Compatibility keeps its filled toggle-family presentation
   (feature/capability semantics): tinted fill + interactive affordance. */
.cm-chip.cm-chip--compatibility {
  cursor: pointer;
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.18));
}

/* ── I3: Generic focus-visible fallback ──────────────────── */
/* Frozen catch-all for previously weak keyboard targets. Arms: the literal
   frozen scope; the real Studio dialog root (.comfymodal-studio-modal); and
   the shell page container (.comfymodal-studio-pagecontainer), which hosts
   every page surface in both the production dialog and the standalone
   harness. Pointer users get no permanent ring (:focus-visible only).
   Specific feature rules override this cleanly via the cascade — outline is
   a single property, so no double ring can result. */
.comfymodal-studio :is(button, [role="button"], [tabindex="0"], a):focus-visible,
.comfymodal-studio-modal :is(button, [role="button"], [tabindex="0"], a):focus-visible,
.comfymodal-studio-pagecontainer :is(button, [role="button"], [tabindex="0"], a):focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

/* ── I3: Shared empty-state base ─────────────────────────── */
/* Minimal foundation only — page cards are redesigned by their own lanes.
   No illustrations, no icons, caller-supplied copy exclusively. */

.cm-empty-state {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #555;
  font-size: 12px;
}
.cm-empty-state-title {
  font-weight: 600;
  color: #999;
}
.cm-empty-state-detail {
  color: #555;
  font-size: 11px;
}
.cm-empty-state-action {
  margin-top: 6px;
}

/* ── Phase I5 — Image compare/viewer region ────────────────────────────── */
/* Lightweight client-only A/B comparison (transient session tray + modal   */
/* view). Uses existing Studio tokens only; no second design system.        */

.cm-compare-tray {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: 14px;
  z-index: 10070;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  max-width: calc(100vw - 24px);
  padding: 6px 10px;
  background: #1a1a1a;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  font-size: 11px;
  color: #ccc;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
}
.cm-compare-tray-title {
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.cm-compare-tray-slot {
  white-space: nowrap;
}
.cm-compare-tray-btn {
  font-size: 11px;
  padding: 3px 10px;
}
.cm-compare-replace-hint {
  margin-left: 6px;
  font-size: 10px;
  color: #999;
  border: 1px solid #444;
  border-radius: 999px;
  padding: 0 6px;
  white-space: nowrap;
}

.cm-compare-overlay {
  position: fixed;
  inset: 0;
  z-index: 10080;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cm-compare-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
}
.cm-compare-dialog {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(1100px, calc(100vw - 24px));
  max-height: calc(100vh - 24px);
  padding: 12px;
  background: #141414;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  box-sizing: border-box;
}
.cm-compare-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.cm-compare-title {
  font-size: 13px;
  font-weight: 600;
  color: #ddd;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cm-compare-close {
  background: transparent;
  border: none;
  color: #ccc;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 6px;
}
.cm-compare-stage {
  position: relative;
  width: 100%;
  height: min(66vh, 720px);
  background: #0c0c0e;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  overflow: hidden;
  touch-action: none;
  user-select: none;
}
.cm-compare-frame {
  position: absolute;
  inset: 0;
}
.cm-compare-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}
.cm-compare-bwrap {
  position: absolute;
  inset: 0;
}
.cm-compare-unavailable {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 11px;
  color: #999;
  border: 1px dashed #444;
  border-radius: 6px;
  padding: 6px 10px;
  background: rgba(20, 20, 20, 0.85);
  pointer-events: none;
}
.cm-compare-label {
  position: absolute;
  top: 8px;
  z-index: 3;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: #ddd;
  background: rgba(10, 10, 12, 0.78);
  border: 1px solid #3a3a3a;
  border-radius: 999px;
  padding: 2px 8px;
  pointer-events: none;
  max-width: 46%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cm-compare-label-a {
  left: 8px;
}
.cm-compare-label-b {
  right: 8px;
}
.cm-compare-divider {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  margin-left: -1px;
  background: var(--color-accent, #5a7fdb);
  z-index: 2;
  pointer-events: none;
}
.cm-compare-slider {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 4;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--color-accent, #5a7fdb);
  color: #fff;
  font-size: 13px;
  cursor: ew-resize;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.55);
}
.cm-compare-stage[data-mode="stacked"] .cm-compare-slider {
  cursor: ns-resize;
}
.cm-compare-hint {
  font-size: 11px;
  color: #999;
}

/* Narrow responsive mode (≤640px): stacked presentation with a horizontal
   divider axis; both labels stay visible; nothing overflows horizontally. */
@media (max-width: 640px) {
  .cm-compare-dialog {
    width: calc(100vw - 16px);
    padding: 8px;
  }
  .cm-compare-stage {
    height: min(72vh, 640px);
  }
}
.cm-compare-stage[data-mode="stacked"] .cm-compare-divider {
  top: 50%;
  bottom: auto;
  left: 0;
  right: 0;
  width: auto;
  height: 2px;
  margin-top: -1px;
  margin-left: 0;
}
.cm-compare-stage[data-mode="stacked"] .cm-compare-label-b {
  top: auto;
  bottom: 8px;
}

/* ── Shelf Playground (leaf 1.2.2) ─────────────────────────────── */

.comfymodal-studio-shelf {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #2a2a2a;
}

.comfymodal-studio-shelf-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.comfymodal-studio-shelf-workflow-name {
  font-size: 12px;
  font-weight: 600;
  color: #d0d0d0;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-shelf-autosaved {
  font-size: 10px;
  color: #666;
  font-style: italic;
  white-space: nowrap;
}

.comfymodal-studio-shelf-mini-btn {
  font-size: 10px;
  padding: 2px 8px;
  flex-shrink: 0;
}

.comfymodal-studio-shelf-fields {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comfymodal-studio-shelf-row {
  display: flex;
  gap: 6px;
}

.comfymodal-studio-shelf-row > .comfymodal-studio-shelf-card {
  flex: 1;
  min-width: 0;
}

.comfymodal-studio-shelf-card {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 8px;
}

.comfymodal-studio-shelf-card.is-prompt {
  border-color: #3a3a3a;
}

.comfymodal-studio-shelf-card.is-dragging {
  opacity: 0.5;
}

.comfymodal-studio-shelf-card.is-drop-target,
.comfymodal-studio-shelf-row.is-drop-target {
  outline: 1px dashed var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

.comfymodal-studio-shelf-card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.comfymodal-studio-shelf-drag {
  cursor: grab;
  color: #555;
  font-size: 12px;
  letter-spacing: -2px;
  user-select: none;
  flex-shrink: 0;
}

.comfymodal-studio-shelf-drag:active {
  cursor: grabbing;
}

.comfymodal-studio-shelf-card-label {
  font-size: 11px;
  font-weight: 500;
  color: #a0a0a0;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-shelf-card-body .comfymodal-input {
  width: 100%;
  box-sizing: border-box;
}

.comfymodal-studio-shelf-advanced-wrap {
  margin-top: 4px;
}

.comfymodal-studio-shelf-advanced {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}

/* Stale output: right-side canvas dims until a new run completes. */

.comfymodal-studio-canvas.is-stale img {
  opacity: 0.45;
}

/* Shelf dialogs (picker + reuse prompt). */

.comfymodal-studio-shelf-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 10001;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
}

.comfymodal-studio-shelf-dialog {
  background: #111;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 16px;
  max-width: min(560px, 92vw);
  max-height: 84vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #d0d0d0;
}

/* ── Shelf Experiment (leaf 1.2.2) ─────────────────────────── */

.comfymodal-studio-shelf-exp {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comfymodal-studio-shelf-exp-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.comfymodal-studio-shelf-exp-chip {
  font-size: 11px;
  color: #ccc;
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 3px;
  padding: 2px 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.comfymodal-studio-shelf-exp-axes {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comfymodal-studio-shelf-exp-axis {
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.comfymodal-studio-shelf-exp-axis.is-dimmed {
  opacity: 0.55;
}

.comfymodal-studio-shelf-exp-axis-toggle {
  background: #1a1a1a;
  color: #aaa;
  border: 1px solid #333;
  padding: 4px 10px;
  font-size: 11px;
  border-radius: 3px;
  cursor: pointer;
  align-self: flex-start;
}

.comfymodal-studio-shelf-exp-axis-toggle.is-axis {
  background: var(--color-accent-muted, rgba(90, 127, 219, 0.18));
  border-color: var(--color-accent, #5a7fdb);
  color: var(--color-accent, #5a7fdb);
}

.comfymodal-studio-shelf-exp-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.comfymodal-studio-shelf-exp-pill {
  font-size: 11px;
  color: #d0d0d0;
  background: #0a0a0a;
  border: 1px solid #3a3a3a;
  border-radius: 10px;
  padding: 2px 6px 2px 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-shelf-exp-pill-remove {
  background: transparent;
  border: none;
  color: #888;
  cursor: pointer;
  font-size: 12px;
  padding: 0 2px;
  line-height: 1;
}

.comfymodal-studio-shelf-exp-pill-remove:hover {
  color: #f87171;
}

.comfymodal-studio-shelf-exp-numops {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.comfymodal-studio-shelf-exp-unique {
  border-top: 1px solid #2a2a2a;
  padding-top: 4px;
}

.comfymodal-studio-shelf-exp-unique-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #a0a0a0;
  padding: 3px 0;
}

.comfymodal-studio-shelf-exp-unique-row .comfymodal-input {
  flex: 1;
  min-width: 0;
}

.comfymodal-studio-shelf-exp-matrix {
  font-size: 12px;
  color: #d0d0d0;
  font-weight: 600;
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
