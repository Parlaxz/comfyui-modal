// Modal GPU — Tokenized Dark Design System
//
// This stylesheet centralizes all visual rules for the Modal GPU frontend.
// Every screen imports ensureTestingStyles() to inject these shared tokens
// and utility classes. No screen should define its own color/layout tokens.

const STYLE_ID = "comfymodal-testing-styles";

const CSS = `
/* ── Design Tokens ─────────────────────────────────────────── */

:root {
  /* Surface tokens */
  --color-bg-base: #181822;
  --color-bg-toolbar: #1b1b27;
  --color-bg-surface: #20202c;
  --color-bg-raised: #252532;
  --color-bg-overlay: rgba(0, 0, 0, 0.72);
  --color-bg-input: #171723;
  --color-bg-hover: #2a2a38;
  --color-bg-selected: #242c3d;

  /* Border tokens */
  --color-border-default: #2d2d3a;
  --color-border-strong: #353545;
  --color-border-interactive: #454559;
  --color-border-focus: #5a7fdb;
  --color-border-danger: #ef4444;

  /* Text tokens */
  --color-text-primary: #e1e4ea;
  --color-text-secondary: #9aa3b2;
  --color-text-muted: #6f7785;

  /* Accent tokens */
  --color-accent: #5a7fdb;
  --color-accent-hover: #6a8ceb;
  --color-accent-active: #4d6fbe;
  --color-accent-muted: rgba(90, 127, 219, 0.18);
  --color-focus-ring: rgba(90, 127, 219, 0.24);
  --color-selection: rgba(90, 127, 219, 0.14);

  /* Semantic tokens */
  --color-success: #4ade80;
  --color-success-bg: rgba(74, 222, 128, 0.12);
  --color-warning: #f59e0b;
  --color-warning-bg: rgba(245, 158, 11, 0.12);
  --color-danger: #ef4444;
  --color-danger-bg: rgba(239, 68, 68, 0.12);
  --color-info-bg: rgba(90, 127, 219, 0.12);

  /* Disabled tokens */
  --color-disabled-bg: #1c1c28;
  --color-disabled-text: #616877;

  /* Spacing tokens */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 20px;
  --space-2xl: 24px;

  /* Radius tokens */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;

  /* Typography tokens */
  --font-size-xs: 11px;
  --font-size-sm: 12px;
  --font-size-base: 13px;
  --font-size-lg: 14px;
  --font-size-xl: 16px;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --line-height-tight: 1.25;
  --line-height-base: 1.45;

  /* Dimension tokens */
  --control-height-sm: 28px;
  --control-height-md: 36px;
  --header-height: 52px;
  --tab-height: 40px;
  --sidebar-width: 188px;
  --modal-max-width: 1240px;
  --modal-height: 90vh;

  /* Motion tokens */
  --duration-fast: 120ms;
  --duration-normal: 180ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
}

/* ── Shared Surface Classes ──────────────────────────────── */

.comfymodal-testing-overlay {
  position: fixed;
  inset: 0;
  background: var(--color-bg-overlay);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.comfymodal-testing-modal {
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

.comfymodal-testing-header {
  display: flex;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--color-border-default);
  flex-shrink: 0;
  background: var(--color-bg-toolbar);
}

.comfymodal-testing-header h2 {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  flex: 1;
  color: var(--color-text-primary);
  letter-spacing: 0.01em;
}

.comfymodal-testing-close {
  background: transparent;
  border: 1px solid var(--color-border-interactive);
  color: var(--color-text-secondary);
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
}

.comfymodal-testing-close:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.comfymodal-testing-close:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

/* ── Tab Navigation ──────────────────────────────────────── */

.comfymodal-testing-nav {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-border-default);
  flex-shrink: 0;
  padding: 0 var(--space-md);
  background: var(--color-bg-base);
  min-height: var(--tab-height);
}

.comfymodal-testing-nav-btn {
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
  position: relative;
}

.comfymodal-testing-nav-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.comfymodal-testing-nav-btn.active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
  font-weight: var(--font-weight-semibold);
}

.comfymodal-testing-nav-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}

/* ── Body / Scroll ────────────────────────────────────────── */

.comfymodal-testing-body {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  background: var(--color-bg-base);
}

/* Thin styled scrollbar */
.comfymodal-testing-body::-webkit-scrollbar {
  width: 6px;
}

.comfymodal-testing-body::-webkit-scrollbar-track {
  background: transparent;
}

.comfymodal-testing-body::-webkit-scrollbar-thumb {
  background: var(--color-border-default);
  border-radius: 3px;
}

.comfymodal-testing-body::-webkit-scrollbar-thumb:hover {
  background: var(--color-border-strong);
}

/* ── Sidebar Panel ───────────────────────────────────────── */

.comfymodal-testing-sidebar-panel {
  padding: var(--space-sm) var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comfymodal-testing-sidebar-panel button {
  background: var(--color-accent);
  border: 1px solid var(--color-accent-hover);
  color: #fff;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  width: 100%;
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-testing-sidebar-panel button:hover {
  background: var(--color-accent-hover);
}

.comfymodal-testing-sidebar-panel button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

.comfymodal-testing-sidebar-panel .status-row {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  padding: 2px 0;
}

/* ── Loader & Error ──────────────────────────────────────── */

.comfymodal-testing-loader {
  padding: 20px;
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
}

.comfymodal-testing-error {
  padding: 20px;
  text-align: center;
}

.comfymodal-testing-error p {
  color: var(--color-danger);
  margin: 0 0 12px;
  font-size: var(--font-size-base);
}

.comfymodal-testing-retry-btn {
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-primary);
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-testing-retry-btn:hover {
  background: var(--color-bg-raised);
}

.comfymodal-testing-retry-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

/* ── Fallback Launcher ────────────────────────────────────── */

.comfymodal-testing-fallback {
  position: fixed;
  right: 8px;
  bottom: 8px;
  z-index: 10000;
}

.comfymodal-testing-fallback button {
  background: var(--color-accent);
  border: 1px solid var(--color-accent-hover);
  color: #fff;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-testing-fallback button:hover {
  background: var(--color-accent-hover);
}

.comfymodal-testing-fallback button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

/* ═══════════════════════════════════════════════════════════ */
/* SHARED VISUAL COMPONENTS                                     */
/* ═══════════════════════════════════════════════════════════ */

/* ── Hero Card (blocked/unhealthy deploy state) ──────────── */

.comfymodal-hero {
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.comfymodal-hero h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

/* ── Button Variants ─────────────────────────────────────── */

.comfymodal-primary-btn {
  background: var(--color-accent);
  border: 1px solid var(--color-accent);
  color: #fff;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard);
}

.comfymodal-primary-btn:hover {
  background: var(--color-accent-hover);
  border-color: var(--color-accent-hover);
}

.comfymodal-primary-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.comfymodal-primary-btn:disabled {
  background: var(--color-disabled-bg);
  border-color: var(--color-border-default);
  color: var(--color-disabled-text);
  cursor: not-allowed;
}

.comfymodal-secondary-btn {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-interactive);
  color: var(--color-text-secondary);
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
}

.comfymodal-secondary-btn:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-strong);
  color: var(--color-text-primary);
}

.comfymodal-secondary-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.comfymodal-secondary-btn:disabled {
  background: var(--color-disabled-bg);
  border-color: var(--color-border-default);
  color: var(--color-disabled-text);
  cursor: not-allowed;
}

.comfymodal-destructive-btn {
  background: transparent;
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
}

.comfymodal-destructive-btn:hover {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.comfymodal-destructive-btn:focus-visible {
  outline: 2px solid var(--color-danger);
  outline-offset: 2px;
}

.comfymodal-destructive-btn:disabled {
  border-color: var(--color-border-default);
  color: var(--color-disabled-text);
  background: var(--color-disabled-bg);
  cursor: not-allowed;
}

/* ── Status Badge ────────────────────────────────────────── */

.comfymodal-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  line-height: var(--line-height-tight);
}

.comfymodal-status-badge.success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.comfymodal-status-badge.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.comfymodal-status-badge.danger {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.comfymodal-status-badge.info {
  background: var(--color-info-bg);
  color: var(--color-accent);
}

/* ── Input / Select / Textarea ──────────────────────────── */

.comfymodal-input,
.comfymodal-testing-input,
.testing-setup-input,
.testing-setup-textarea,
.testing-setup-select,
.testing-results-select {
  background: var(--color-bg-input);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-primary);
  padding: 6px 10px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-base);
  transition: border-color var(--duration-fast) var(--ease-standard),
              box-shadow var(--duration-fast) var(--ease-standard);
}

.comfymodal-input:focus,
.comfymodal-testing-input:focus,
.testing-setup-input:focus,
.testing-setup-textarea:focus,
.testing-setup-select:focus,
.testing-results-select:focus {
  outline: none;
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-focus-ring);
}

.comfymodal-input:hover,
.comfymodal-testing-input:hover,
.testing-setup-input:hover,
.testing-setup-textarea:hover,
.testing-setup-select:hover,
.testing-results-select:hover {
  border-color: var(--color-border-interactive);
}

.comfymodal-input.input-error,
.comfymodal-testing-input.input-error,
.testing-setup-input.input-error {
  border-color: var(--color-border-danger);
  box-shadow: 0 0 0 2px var(--color-danger-bg);
}

/* ── Focus-visible ring (global) ────────────────────────── */

:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

/* ── Progress Bar ────────────────────────────────────────── */

.comfymodal-progress-bar {
  width: 100%;
  height: 6px;
  background: var(--color-bg-input);
  border-radius: 3px;
  overflow: hidden;
}

.comfymodal-progress-bar .comfymodal-progress-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: 3px;
  transition: width var(--duration-normal) var(--ease-standard);
}

.comfymodal-progress-bar .comfymodal-progress-fill.success {
  background: var(--color-success);
}

.comfymodal-progress-bar .comfymodal-progress-fill.warning {
  background: var(--color-warning);
}

/* ── Section Card ────────────────────────────────────────── */

.comfymodal-section-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.comfymodal-section-card-header {
  display: flex;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-toolbar);
  border-bottom: 1px solid var(--color-border-default);
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.comfymodal-section-card-body {
  padding: var(--space-md);
}

/* ── Dashboard Cards ─────────────────────────────────────── */

.comfymodal-dashboard-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
}

.comfymodal-dashboard-card h3 {
  margin: 0 0 var(--space-sm);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

/* ── Utility Toolbar ─────────────────────────────────────── */

.comfymodal-utility-toolbar {
  display: flex;
  gap: var(--space-sm);
  flex-wrap: wrap;
  align-items: center;
}

.comfymodal-utility-toolbar .comfymodal-secondary-btn {
  padding: 6px 12px;
  font-size: var(--font-size-xs);
}

/* ── Deployment Strip ────────────────────────────────────── */

.comfymodal-deploy-strip {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

/* ── Settings Wrapper ────────────────────────────────────── */

.comfymodal-settings-wrapper {
  display: flex;
  gap: var(--space-lg);
  height: 100%;
}

.comfymodal-settings-wrapper .testing-settings-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 160px;
  flex-shrink: 0;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  padding: var(--space-sm);
}

.comfymodal-settings-wrapper .testing-settings-nav .testing-settings-nav-btn {
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  text-align: left;
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
}

.comfymodal-settings-wrapper .testing-settings-nav .testing-settings-nav-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.comfymodal-settings-wrapper .testing-settings-nav .testing-settings-nav-btn.active,
.comfymodal-settings-wrapper .testing-settings-nav .testing-settings-nav-btn.comfymodal-nav-btn-active {
  background: var(--color-selection);
  color: var(--color-accent);
  font-weight: var(--font-weight-semibold);
}

.comfymodal-settings-wrapper .testing-settings-body {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

/* ── History Row ─────────────────────────────────────────── */

.comfymodal-history-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-history-row:hover {
  background: var(--color-bg-hover);
}

.comfymodal-history-row .testing-history-thumb {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-input);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  overflow: hidden;
}

.comfymodal-history-row .testing-history-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.comfymodal-history-row .testing-history-kind {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 48px;
}

.comfymodal-history-row .testing-history-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  flex-shrink: 0;
  min-width: 60px;
}

.comfymodal-history-row .testing-history-status .status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.comfymodal-history-row .testing-history-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 80px;
  font-variant-numeric: tabular-nums;
}

.comfymodal-history-row .testing-history-duration {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 50px;
  font-variant-numeric: tabular-nums;
}

.comfymodal-history-row .testing-history-model {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Results Layers ──────────────────────────────────────── */

.testing-results-root {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.testing-results-root [data-section="controls"] {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
}

.testing-results-root [data-section="progress"] {
  padding: var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
}

.testing-results-root [data-section="grid"] {
  background: transparent;
}

/* ── Results: visual hierarchy improvements ──────────────── */

.testing-results-root [data-section="command-bar"] {
  padding: var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-md);
}

.testing-results-root [data-section="summary"] {
  padding: var(--space-lg);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-md);
}

.testing-results-root [data-section="summary"] .testing-results-summary-card {
  gap: var(--space-xl);
  padding: 0;
  background: transparent;
  border: none;
}

.testing-results-root [data-section="summary"] .testing-results-summary-primary .summary-stat-value {
  font-size: 28px;
  font-weight: var(--font-weight-semibold);
}

.testing-results-root [data-section="summary"] .summary-stat-value {
  font-size: var(--font-size-xl);
}

.testing-results-root [data-section="summary"] .summary-stat-label {
  font-size: var(--font-size-sm);
  letter-spacing: 0.06em;
}

/* ── Setup: field grid utility ───────────────────────────── */

.testing-setup-field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-md);
}

/* ── Setup: finish zone ──────────────────────────────────── */

.testing-setup-finish-zone {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-lg);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
}

/* ── Setup: contextual profile toolbar ───────────────────── */

.testing-setup-profile-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
  margin-bottom: var(--space-sm);
}

/* ── Results: command bar groups ─────────────────────────── */

.testing-results-command-bar {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
}

.testing-results-command-main {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
}

.testing-results-command-danger {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
  padding-top: var(--space-xs);
  border-top: 1px solid var(--color-border-default);
}

/* ── Results: summary card ───────────────────────────────── */

.testing-results-summary-card {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  padding: var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-sm);
}

.testing-results-summary-card .summary-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.testing-results-summary-card .summary-stat-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-weight: var(--font-weight-medium);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.testing-results-summary-card .summary-stat-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-results-summary-card .summary-stat-value.completed {
  color: var(--color-success);
}

.testing-results-summary-card .summary-stat-value.failed {
  color: var(--color-danger);
}

.testing-results-summary-card .summary-stat-value.skipped {
  color: var(--color-text-muted);
}

/* ── Results: gallery ────────────────────────────────────── */

.testing-results-gallery {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── Results: empty state ────────────────────────────────── */

.testing-results-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-2xl) var(--space-lg);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
  border: 1px dashed var(--color-border-default);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
}

/* ── Page-level surface primitives ───────────────────────── */

.testing-dashboard-page,
.testing-setup-page,
.testing-profiles-page,
.testing-results-page,
.testing-history-page,
.testing-settings-page {
  height: 100%;
  overflow-y: auto;
  padding: var(--space-xl);
  box-sizing: border-box;
}

/* ── Settings: root layout ────────────────────────────────── */

.testing-settings-root {
  height: 100%;
  overflow: hidden;
}

.testing-settings-root .comfymodal-settings-wrapper {
  height: 100%;
}

.testing-settings-root .testing-settings-nav {
  overflow-y: auto;
  max-height: 100%;
}

.testing-settings-root .testing-settings-body {
  overflow-y: auto;
  max-height: 100%;
  padding: var(--space-sm);
}

/* ── Profiles: workspace ─────────────────────────────────── */

.testing-profiles-root {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  height: 100%;
}

.testing-profiles-create-card,
.testing-profiles-list,
.testing-profiles-editor {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
}

.testing-profiles-workspace {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: var(--space-md);
  min-height: 0;
  flex: 1;
}

.testing-profiles-list,
.testing-profiles-editor {
  min-height: 0;
  overflow-y: auto;
}

.testing-profiles-pane-title,
.testing-profiles-section-title,
.testing-profiles-editor-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-profiles-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.testing-profiles-field-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.testing-profiles-inline-actions,
.testing-profiles-row-actions {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
}

.testing-profiles-list-rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}

.testing-profiles-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-raised);
}

.testing-profiles-row-active {
  border-color: var(--color-accent);
}

.testing-profiles-row-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}

.testing-profiles-row-name {
  background: transparent;
  border: none;
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  text-align: left;
  cursor: pointer;
  padding: 0;
}

.testing-profiles-row-summary,
.testing-profiles-editor-summary,
.testing-profiles-section-help,
.testing-profiles-status,
.testing-profiles-empty-state,
.testing-profiles-warning-box,
.testing-profiles-error-box {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.testing-profiles-warning-box {
  color: var(--color-warning);
}

.testing-profiles-error-box {
  color: var(--color-danger);
}

.testing-profiles-model-section,
.testing-profiles-mapping-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px solid var(--color-border-default);
}

.testing-profiles-model-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-sm);
}

.testing-profiles-mapping-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.testing-profiles-mapping-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: var(--space-sm);
  align-items: center;
}

.testing-profiles-slot-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
}

@media (max-width: 900px) {
  .testing-profiles-workspace {
    grid-template-columns: 1fr;
  }

  .testing-profiles-model-grid,
  .testing-profiles-mapping-row {
    grid-template-columns: 1fr;
  }
}

/* ── Dashboard: primary actions group ────────────────────── */

.testing-dashboard-primary-actions {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  margin-bottom: var(--space-lg);
}

.testing-dashboard-primary-actions .testing-dashboard-cta-main {
  padding: 12px 28px;
  font-size: var(--font-size-lg);
}

.testing-dashboard-secondary-actions {
  display: flex;
  gap: var(--space-sm);
}

/* ── Dashboard: utility toolbar (subordinate) ────────────── */

.testing-dashboard-utility-toolbar {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
  opacity: 0.75;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.testing-dashboard-utility-toolbar:hover {
  opacity: 1;
}

/* ── Dashboard: metrics hierarchy ────────────────────────── */

.testing-dashboard-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.testing-dashboard-metric {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
}

.testing-dashboard-metric h3 {
  margin: 0 0 var(--space-sm);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.testing-dashboard-metric-primary {
  background: var(--color-bg-raised);
  border-color: var(--color-border-strong);
}

.testing-dashboard-metric-primary h3 {
  color: var(--color-text-primary);
}

/* ── Setup: collapsible section cards ────────────────────── */

.testing-setup-section-collapsible {
  transition: opacity var(--duration-normal) var(--ease-standard);
}

.testing-setup-section-collapsible[data-collapsed="true"] {
  opacity: 0.5;
}

.testing-setup-section-collapsible[data-collapsed="true"] .comfymodal-section-card-body {
  display: none;
}

.testing-setup-section-collapsible[data-collapsed="false"] {
  opacity: 1;
}

/* ── Setup: name/notes large inputs ────────────────────────── */

.testing-setup-name-input {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  padding: 10px 14px;
  min-height: 40px;
  width: 100%;
}

.testing-setup-notes-textarea {
  font-size: var(--font-size-base);
  padding: 10px 14px;
  min-height: 80px;
  width: 100%;
  resize: vertical;
  line-height: var(--line-height-base);
}

.testing-setup-field-large {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.testing-setup-field-large .testing-setup-field-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* ── Setup: experiment fields ──────────────────────────────── */

.testing-setup-experiment-fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── Setup: model profiles section ────────────────────────── */

.testing-setup-model-profiles {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-model-profile-entry {
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.testing-setup-model-profile-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-accent);
}

/* ── Setup: sampler grid with enable/disable ──────────────── */

.testing-setup-sampler-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-xs) var(--space-sm);
}

.testing-setup-sampler-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}

.testing-setup-sampler-row:hover {
  background: var(--color-bg-hover);
}

.testing-setup-sampler-row.testing-setup-sampler-disabled {
  opacity: 0.45;
}

.testing-setup-sampler-row.testing-setup-sampler-enabled {
  opacity: 1;
}

.testing-setup-sampler-toggle {
  accent-color: var(--color-accent);
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.testing-setup-sampler-name {
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.testing-setup-sampler-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.testing-setup-sampler-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
}

.testing-setup-sampler-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-weight: var(--font-weight-normal);
}

/* ── Setup: prompt editor ──────────────────────────────────── */

.testing-setup-prompt-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-prompt-textarea {
  min-height: 72px;
  width: 100%;
  resize: vertical;
  line-height: var(--line-height-base);
  font-size: var(--font-size-base);
}

/* ── Setup: preset bar ─────────────────────────────────────── */

.testing-setup-preset-bar {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-border-default);
}

.testing-setup-preset-dropdown {
  flex: 1;
  min-width: 160px;
}

.testing-setup-save-preset-btn {
  flex-shrink: 0;
}

/* ── Setup: workflow profile rows ──────────────────────────── */

.testing-setup-create-row {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  margin-bottom: var(--space-sm);
}

.testing-setup-profiles {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.testing-setup-profile-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  transition: border-color var(--duration-fast) var(--ease-standard);
}

.testing-setup-profile-row.testing-setup-profile-selected {
  border-color: var(--color-accent);
  background: var(--color-accent-muted);
}

.testing-setup-profile-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.testing-setup-profile-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-setup-profile-triple {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.testing-setup-profile-actions {
  display: flex;
  gap: var(--space-xs);
  flex-shrink: 0;
}

.testing-setup-profile-action-btn {
  padding: 4px 10px !important;
  font-size: var(--font-size-xs) !important;
}

/* ── Setup: sections container ─────────────────────────────── */

.testing-setup-sections {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── Setup: empty hints ────────────────────────────────────── */

.testing-setup-empty-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  padding: var(--space-sm) 0;
}

/* ── Setup: section status messages ────────────────────────── */

.testing-setup-section-status {
  font-size: var(--font-size-xs);
  padding: 4px 0;
  min-height: 20px;
}

.testing-setup-status-ok {
  color: var(--color-success);
}

.testing-setup-status-error {
  color: var(--color-danger);
}

.testing-setup-status-warn {
  color: var(--color-warning);
}

.testing-setup-status-info {
  color: var(--color-accent);
}

/* ── Setup: profile action menu ──────────────────────────── */

.testing-setup-profile-menu {
  display: inline-block;
  position: relative;
}

.testing-setup-profile-menu summary {
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-default);
  user-select: none;
}

.testing-setup-profile-menu summary:hover {
  border-color: var(--color-border-interactive);
  color: var(--color-text-secondary);
}

.testing-setup-profile-menu[open] summary {
  border-color: var(--color-accent);
}

.testing-setup-profile-menu .profile-menu-body {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 20;
  min-width: 160px;
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  padding: var(--space-xs);
  display: flex;
  flex-direction: column;
  gap: 2px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}

/* ── Setup: advanced toggle ──────────────────────────────── */

.testing-setup-advanced-toggle {
  margin-top: var(--space-sm);
  border-top: 1px solid var(--color-border-default);
  padding-top: var(--space-sm);
}

.testing-setup-advanced-toggle summary {
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-weight: var(--font-weight-medium);
  user-select: none;
}

.testing-setup-advanced-toggle summary:hover {
  color: var(--color-text-secondary);
}

.testing-setup-advanced-toggle .advanced-body {
  margin-top: var(--space-sm);
}

/* ── Setup: prominent finish zone ────────────────────────── */

.testing-setup-finish-zone-prominent {
  border: 2px solid var(--color-accent);
  background: var(--color-bg-raised);
}

/* ── Results: command routine group ──────────────────────── */

.testing-results-command-routine {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
}

/* ── Results: summary primary emphasis ───────────────────── */

.testing-results-summary-primary {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-success);
}

.testing-results-summary-primary .summary-stat-value {
  font-size: 24px;
}

/* ── History: two-line skim row ──────────────────────────── */

.testing-history-row-main {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex: 1;
  min-width: 0;
}

.testing-history-row-meta {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-wrap: wrap;
}

/* ── Reduced Motion ──────────────────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}

/* ── Responsive helpers ─────────────────────────────────── */

@media (max-width: 900px) {
  .comfymodal-settings-wrapper {
    flex-direction: column;
  }

  .comfymodal-settings-wrapper .testing-settings-nav {
    flex-direction: row;
    overflow-x: auto;
    min-width: unset;
  }

  .comfymodal-history-row {
    flex-wrap: wrap;
  }
}
`;

export function ensureTestingStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = CSS;
  document.head.appendChild(style);
}

export function removeTestingStyles() {
  const el = document.getElementById(STYLE_ID);
  if (el) el.remove();
}
