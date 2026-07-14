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

  /* History preview close button */
  .comfymodal-studio-history-preview-close {
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

/* ── Running Config Panel (floating overlay) ──────────────── */
/* Positioned inside .comfymodal-studio-canvas, overlaying the  */
/* output image. Translucent with backdrop blur.                */

.comfymodal-studio-running-config {
  position: absolute;
  top: 8px;
  right: 8px;
  max-width: 280px;
  min-width: 190px;
  min-height: 220px;
  background: rgba(12, 12, 12, 0.88);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border: 1px solid rgba(40, 40, 40, 0.7);
  border-radius: 4px;
  padding: 7px 10px;
  font-size: 11px;
  line-height: 1.5;
  z-index: 10;
  pointer-events: auto;
  display: none;
  box-shadow: 0 2px 14px rgba(0, 0, 0, 0.45);
}

.comfymodal-studio-running-config.is-visible {
  display: block;
}

.comfymodal-studio-running-config-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
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

.comfymodal-studio-running-config-prompt {
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
}

.comfymodal-studio-running-config-prompt-text {
  font-size: 10px;
  color: #d0d0d0;
  word-wrap: break-word;
  max-height: 96px;
  overflow-y: auto;
  display: block;
  margin-top: 1px;
  line-height: 1.4;
}

.comfymodal-studio-running-config-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1px 6px;
  margin-bottom: 3px;
  padding-bottom: 3px;
  border-bottom: 1px solid rgba(26, 26, 26, 0.7);
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

.comfymodal-studio-running-config-axes {
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

.comfymodal-studio-running-config-preset-count {
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
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
  margin-top: 8px;
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

.comfymodal-studio-history-preview {
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

.comfymodal-studio-history-preview-backdrop {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
}

.comfymodal-studio-history-preview-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.comfymodal-studio-history-preview-close {
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

.comfymodal-studio-history-preview-close:hover {
  color: #fff;
}

.comfymodal-studio-history-preview-image {
  max-width: 100%;
  max-height: 80vh;
  border-radius: 4px;
  object-fit: contain;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6);
}

.comfymodal-studio-history-preview-noimage {
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

.comfymodal-studio-history-preview-info {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 11px;
  color: #aaa;
  max-width: 100%;
}

.comfymodal-studio-history-preview-status {
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 10px;
  color: #4ade80;
}

.comfymodal-studio-history-preview-prompt {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comfymodal-studio-history-preview-time {
  color: #666;
  flex-shrink: 0;
}

.comfymodal-studio-history-preview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  justify-content: center;
  margin-top: 4px;
}

.comfymodal-studio-history-preview-meta-item {
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

.comfymodal-studio-legacy-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.comfymodal-studio-legacy-list li {
  padding: 6px 12px;
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  font-size: 12px;
  color: #888;
  cursor: pointer;
  transition: background 0.15s;
}

.comfymodal-studio-legacy-list li:hover {
  background: #1a1a1a;
  color: #d0d0d0;
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
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  }
  .comfymodal-studio-filter-bar input,
  .comfymodal-studio-filter-bar select {
    min-height: 44px;
  }
  /* Experiment grid: reduce viewport padding to reclaim space */
  .comfymodal-studio-experiment-grid-viewport {
    padding: 8px 8px;
  }

  /* Floating config panel: span full width at top on narrow screens,
     with capped height to avoid obscuring the output image. */
  .comfymodal-studio-running-config.is-visible {
    top: 0;
    right: 0;
    left: 0;
    max-width: none;
    min-width: 0;
    max-height: 40%;
    overflow-y: auto;
    border-radius: 0 0 4px 4px;
    border-top: none;
  }
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

/* ── Legacy wrapper ──────────────────────────────────────── */

.comfymodal-studio-legacy {
  height: 100%;
  overflow-y: auto;
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

.comfymodal-studio-history-preview-close:focus-visible {
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
  aspect-ratio: auto;
  min-height: 100px;
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

.comfymodal-studio-exp-tile-thumbs {
  display: flex;
  gap: 2px;
  padding: 4px 8px 8px;
  width: 100%;
  box-sizing: border-box;
  overflow: hidden;
}

.comfymodal-studio-exp-tile-thumb {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 2px;
  border: 1px solid #2a2a2a;
  flex-shrink: 0;
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
  gap: 8px;
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
  margin-bottom: 8px;
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
  gap: 2px;
}

.comfymodal-studio-experiment-grid-row {
  display: flex;
  gap: 2px;
  align-items: stretch;
}

.comfymodal-studio-experiment-grid-row-cells {
  display: flex;
  gap: 2px;
  flex: 1;
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
  flex: 1;
  min-width: 80px;
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

/* ── Cell Card ──────────────────────────────────────────── */

.comfymodal-studio-experiment-grid-cell {
  flex: 1 1 var(--cell-min-width, 100px);
  min-width: var(--cell-min-width, 60px);
  max-width: none;
  min-height: var(--cell-min-height, 60px);
  max-height: none;
  aspect-ratio: var(--cell-aspect-ratio, 1/1);
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  background: #0a0a0a;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 3px;
  transition: border-color 0.15s, box-shadow 0.15s;
  position: relative;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  color: inherit;
  overflow: hidden;
}

.comfymodal-studio-experiment-grid-cell:hover {
  border-color: var(--color-accent, #5a7fdb);
  box-shadow: 0 0 8px rgba(90, 127, 219, 0.2);
}

.comfymodal-studio-experiment-grid-cell:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

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
  border-color: var(--color-accent, #5a7fdb);
  box-shadow: 0 0 6px rgba(90, 127, 219, 0.3);
}

.comfymodal-studio-experiment-grid-cell.selected {
  border-color: #fbbf24;
  box-shadow: 0 0 10px rgba(251, 191, 36, 0.3);
}

.comfymodal-studio-experiment-grid-cell-empty {
  cursor: default;
  opacity: 0.35;
  font-size: 10px;
  color: #555;
  min-width: 60px;
  min-height: 60px;
}

.comfymodal-studio-experiment-grid-cell-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 2px;
  display: block;
  flex: 1;
  max-width: 100%;
}

/* Prompt block in cells constrained to a readable max width.
   min-width:0 + width:100% ensures ellipsis works when parent
   cell is narrower than max-width. */
.comfymodal-studio-experiment-grid-cell-prompt {
  font-size: 9px;
  color: #aaa;
  max-width: 280px;
  min-width: 0;
  width: 100%;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.4;
  padding: 2px 4px;
}

.comfymodal-studio-experiment-grid-cell-loading {
  width: 24px;
  height: 24px;
  border: 2px solid #333;
  border-top-color: var(--color-accent, #5a7fdb);
  border-radius: 50%;
  animation: cm-exp-spin 0.8s linear infinite;
}

@keyframes cm-exp-spin {
  to { transform: rotate(360deg); }
}

@keyframes cm-exp-indeterminate {
  0%   { width: 20%; opacity: 0.6; }
  50%  { width: 70%; opacity: 1; }
  100% { width: 20%; opacity: 0.6; }
}

.comfymodal-studio-experiment-grid-cell-done-icon {
  font-size: 18px;
  color: #4ade80;
}

.comfymodal-studio-experiment-grid-cell-fail-icon {
  font-size: 18px;
  color: #f87171;
}

.comfymodal-studio-experiment-grid-cell-skip-icon {
  font-size: 16px;
  color: #fbbf24;
}

.comfymodal-studio-experiment-grid-cell-interrupt-icon {
  font-size: 16px;
  color: #fb923c;
}

.comfymodal-studio-experiment-grid-cell-stack {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 80px;
}

.comfymodal-studio-experiment-grid-cell-stack > .comfymodal-studio-experiment-grid-cell {
  flex: none;
  min-width: 0;
  min-height: 60px;
}

.comfymodal-studio-experiment-grid-cell-placeholder {
  width: 100%;
  height: 100%;
  min-height: 40px;
  border: 1px dashed #2a2a2a;
  border-radius: 2px;
  flex: 1;
}

.comfymodal-studio-experiment-grid-cell-status {
  font-size: 9px;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  flex-shrink: 0;
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

.comfymodal-studio-experiment-grid-detail-overlay {
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

.comfymodal-studio-experiment-grid-detail-backdrop {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
}

.comfymodal-studio-experiment-grid-detail-panel {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.6);
  min-width: 240px;
}

.comfymodal-studio-experiment-grid-detail-panel::-webkit-scrollbar {
  width: 6px;
}
.comfymodal-studio-experiment-grid-detail-panel::-webkit-scrollbar-track {
  background: transparent;
}
.comfymodal-studio-experiment-grid-detail-panel::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 3px;
}

.comfymodal-studio-experiment-grid-detail-close {
  position: absolute;
  top: 8px;
  right: 8px;
  background: transparent;
  border: none;
  color: #aaa;
  font-size: 20px;
  cursor: pointer;
  padding: 6px 10px;
  line-height: 1;
  z-index: 1;
  transition: color 0.15s;
  border-radius: 3px;
}

.comfymodal-studio-experiment-grid-detail-close:hover {
  color: #fff;
}

.comfymodal-studio-experiment-grid-detail-close:focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}

.comfymodal-studio-experiment-grid-detail-image {
  max-width: 100%;
  max-height: 60vh;
  object-fit: contain;
  border-radius: 4px;
}

.comfymodal-studio-experiment-grid-detail-noimage {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  color: #555;
  font-size: 12px;
}

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
